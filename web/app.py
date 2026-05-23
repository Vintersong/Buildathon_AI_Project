import json
import re
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.store import load_record, save_record
from core.match import generate_shortlist
from core.config import (
    RECORDS_DIR,
    REQUIREMENTS_DIR,
    RECORD_INDEX_PATH,
    INTAKE_DIR,
)
from core.ingest import ingest_file
from core.review import get_review_queue, resolve_case
from core.events import log_event

app = FastAPI(title="Bloodhound Talent Pool Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# App config (config.json at project root)
# ---------------------------------------------------------------------------

CONFIG_PATH = project_root / "config.json"

CONFIG_DEFAULTS = {
    "model": "gemini-2.5-flash",
    "confidence_threshold": 0.85,
    "sovereign_cloud": False,
}


class AppConfig(BaseModel):
    model: str = Field(default="gemini-2.5-flash")
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    sovereign_cloud: bool = Field(default=False)


def load_app_config() -> AppConfig:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig(**{**CONFIG_DEFAULTS, **data})
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return AppConfig(**CONFIG_DEFAULTS)


def save_app_config(cfg: AppConfig) -> None:
    from filelock import FileLock
    lock = FileLock(f"{CONFIG_PATH}.lock")
    with lock:
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, indent=2)
        tmp.replace(CONFIG_PATH)


@app.get("/api/config", response_model=AppConfig)
async def get_config():
    return load_app_config()


@app.post("/api/config", response_model=AppConfig)
async def post_config(body: AppConfig):
    try:
        save_app_config(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")
    return body


# ---------------------------------------------------------------------------
# Data mapping helpers
# ---------------------------------------------------------------------------

def _initials(name: Optional[str]) -> str:
    if not name:
        return "??"
    parts = name.strip().split()
    return "".join(p[0] for p in parts if p)[:2].upper()


def _compliance_status(record) -> str:
    if record.compliance.human_review_required:
        return "PENDING REVIEW"
    if record.compliance.retention_until:
        try:
            exp = datetime.fromisoformat(record.compliance.retention_until.replace("Z", "+00:00"))
            days_left = (exp - datetime.now(timezone.utc)).days
            if days_left <= 14:
                return "EXPIRING (14D)"
        except Exception:
            pass
    return "COMPLIANT"


def _map_candidate(record_id: str, rec) -> dict:
    return {
        "id": record_id,
        "name": rec.identity.primary_name or "Unknown",
        "imageInitials": _initials(rec.identity.primary_name),
        "seniority": rec.profile.seniority or "Unknown",
        "topSkills": [s.upper() for s in (rec.profile.technologies_used or [])[:3]],
        "matchScore": rec.scores.last_match_score or rec.scores.identity_confidence or 0.0,
        "complianceStatus": _compliance_status(rec),
        "actionsRequired": rec.compliance.human_review_required,
    }


def _candidate_record_ids() -> list[str]:
    seen: set[str] = set()
    record_ids: list[str] = []

    if RECORD_INDEX_PATH.exists():
        try:
            with open(RECORD_INDEX_PATH, "r", encoding="utf-8") as f:
                index = json.load(f)
            indexed_ids = index.keys() if isinstance(index, dict) else index
            for record_id in indexed_ids:
                if isinstance(record_id, str) and record_id not in seen:
                    seen.add(record_id)
                    record_ids.append(record_id)
        except (json.JSONDecodeError, OSError):
            pass

    if RECORDS_DIR.exists():
        for record_file in sorted(RECORDS_DIR.glob("*.json")):
            record_id = record_file.stem
            if record_id not in seen:
                seen.add(record_id)
                record_ids.append(record_id)

    return record_ids


def _map_review_task(case: dict) -> dict:
    reason = case.get("reason", "")
    if "identity" in reason:
        task_type = "IDENTITY_CONFLICT"
    elif any(k in reason for k in ("pii", "consent", "compliance", "retention", "gdpr",
                                    "sensitive", "low_extraction", "data_region", "missing")):
        task_type = "COMPLIANCE_FLAG"
    elif "outreach" in reason:
        task_type = "OUTREACH_DRAFT"
    else:
        task_type = "COMPLIANCE_FLAG"

    status = "pending" if case.get("status") == "open" else "resolved"
    created_at = case.get("created_at", datetime.utcnow().isoformat() + "Z")

    task: dict[str, Any] = {
        "id": case.get("case_id", ""),
        "type": task_type,
        "title": f"{task_type.replace('_', ' ').title()}: {case.get('record_id', '')}",
        "timestamp": created_at,
        "timeAgo": _time_ago(created_at),
        "confidence": 1.0,
        "status": status,
    }

    if task_type == "COMPLIANCE_FLAG":
        rec = load_record(case.get("record_id", ""))
        name = rec.identity.primary_name if rec else case.get("record_id", "")
        task["complianceDetails"] = {
            "candidateName": name,
            "reason": reason,
            "quarantineValue": "",
            "details": reason,
        }
    elif task_type == "OUTREACH_DRAFT":
        rec = load_record(case.get("record_id", ""))
        name = rec.identity.primary_name if rec else case.get("record_id", "")
        task["outreachDetails"] = {
            "targetName": name,
            "subject": f"Opportunity for {name}",
            "draftBody": case.get("draft_text") or case.get("draft_body", ""),
            "signals": [],
        }
    elif task_type == "IDENTITY_CONFLICT":
        rec = load_record(case.get("record_id", ""))
        name = rec.identity.primary_name if rec else case.get("record_id", "")
        task["existingRecord"] = {
            "uuid": case.get("record_id", ""),
            "name": name,
            "currentRole": rec.profile.headline if rec else "",
            "location": rec.profile.location if rec else "",
            "linkedin": rec.identity.linkedin_url if rec else "",
        }

    return task


def _map_audit_event(line: str) -> Optional[dict]:
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        return None
    actor_raw = e.get("actor", {})
    if isinstance(actor_raw, dict):
        actor_type = actor_raw.get("type", "system")
    else:
        actor_type = str(actor_raw)
    actor_map = {"system": "SYS", "human": "HUMAN", "security": "SEC"}
    actor = actor_map.get(actor_type.lower(), "SYS")

    source = e.get("source", {})
    changes = e.get("changes", [])
    summary_parts = []
    if isinstance(source, dict) and source.get("file_name"):
        summary_parts.append(f"File: {source['file_name']}")
    if changes:
        summary_parts.append(f"{len(changes)} change(s)")
    payload_summary = "; ".join(summary_parts) or e.get("event_type", "event")

    return {
        "id": e.get("event_id", ""),
        "timestamp": e.get("timestamp", ""),
        "action": e.get("event_type", ""),
        "actor": actor,
        "payloadSummary": payload_summary,
        "confidence": float(e.get("confidence", 1.0)),
    }


def _time_ago(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - t
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            return f"{seconds // 60} minutes ago"
        if seconds < 86400:
            return f"{seconds // 3600} hours ago"
        return f"{seconds // 86400} days ago"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Candidate endpoints
# ---------------------------------------------------------------------------

@app.get("/api/candidates")
async def list_candidates():
    candidates = []
    for record_id in _candidate_record_ids():
        rec = load_record(record_id)
        if rec and not rec.state.archived:
            candidates.append(_map_candidate(record_id, rec))
    return candidates


@app.post("/api/candidates/ingest")
async def ingest_candidate(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported")

    cvs_dir = INTAKE_DIR / "cvs"
    cvs_dir.mkdir(parents=True, exist_ok=True)

    dest = cvs_dir / f"upload_{uuid.uuid4().hex[:8]}{suffix}"
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        record_id = ingest_file(dest, source_type="document")
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=500, detail="Record not found after ingest")
    return _map_candidate(record_id, rec)


class StatusPatch(BaseModel):
    complianceStatus: str


@app.patch("/api/candidates/{record_id}/status")
async def patch_candidate_status(record_id: str, body: StatusPatch):
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    status = body.complianceStatus.upper().strip()

    if status == "COMPLIANT":
        rec.compliance.human_review_required = False
    elif status == "PENDING REVIEW":
        rec.compliance.human_review_required = True
    elif status in ("EXPIRING (14D)", "EXPIRING"):
        pass
    else:
        raise HTTPException(status_code=400, detail=f"Unknown complianceStatus: '{body.complianceStatus}'")

    rec.updated_at = datetime.utcnow().isoformat() + "Z"

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "compliance_status_override",
        "timestamp": rec.updated_at,
        "actor": {"type": "human"},
        "source": {"record_id": record_id},
        "changes": [{"field": "complianceStatus", "new_value": status}],
        "confidence": 1.0,
    }

    try:
        save_record(record_id, rec, event=event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist record: {str(e)}")

    return _map_candidate(record_id, rec)


# ---------------------------------------------------------------------------
# Job requirement endpoints
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    title: str
    department: str
    location: str
    status: str = "MATCHING"
    tags: List[str] = []
    must_have: List[str] = []
    nice_to_have: List[str] = []


def _map_job(req_id: str, data: dict) -> dict:
    reqs = data.get("requirements", {})
    return {
        "id": req_id,
        "title": data.get("title", ""),
        "department": data.get("department") or data.get("description", ""),
        "location": reqs.get("location", ""),
        "status": "MATCHING",
        "tags": reqs.get("must_have", [])[:2],
        "candidatesProcessed": 0,
        "shortlist": [],
    }


@app.get("/api/jobs")
async def list_jobs():
    jobs = []
    if not REQUIREMENTS_DIR.exists():
        return jobs
    for req_file in sorted(REQUIREMENTS_DIR.glob("*.json")):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            jobs.append(_map_job(req_file.stem, data))
        except Exception:
            continue
    return jobs


@app.post("/api/jobs")
async def create_job(body: JobCreate):
    now = datetime.utcnow().isoformat() + "Z"
    req_id = f"req_{uuid.uuid4().hex[:12]}"
    record = {
        "id": req_id,
        "title": body.title,
        "department": body.department,
        "description": body.department,
        "requirements": {
            "must_have": body.must_have,
            "nice_to_have": body.nice_to_have,
            "location": body.location,
            "language": [],
            "category": None,
        },
        "scoring": {},
        "created_at": now,
        "updated_at": now,
    }
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REQUIREMENTS_DIR / f"{req_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return {
        "id": req_id,
        "title": body.title,
        "department": body.department,
        "location": body.location,
        "status": body.status,
        "tags": body.tags,
        "candidatesProcessed": 0,
        "shortlist": [],
    }


@app.post("/api/jobs/{req_id}/shortlist")
async def run_shortlist(req_id: str):
    try:
        result = generate_shortlist(req_id, top_n=5)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    shortlist = []
    for item in result.get("shortlist", []):
        rec_id = item.get("record_id", "")
        rec = load_record(rec_id)
        name = rec.identity.primary_name if rec else rec_id
        shortlist.append({
            "id": rec_id,
            "name": name,
            "confidence": item.get("match_score", 0.0),
            "explanation": "; ".join(item.get("evidence", [])),
            "status": "pending_review" if item.get("review_required") else "active",
            "initials": _initials(name),
        })
    return shortlist


# ---------------------------------------------------------------------------
# Review queue endpoints
# ---------------------------------------------------------------------------

@app.get("/api/review")
async def list_review_tasks():
    cases = get_review_queue()
    return [_map_review_task(c) for c in cases]


class ResolveBody(BaseModel):
    resolution: str
    reviewer: str = "human_operator"


@app.post("/api/review/{case_id}/resolve")
async def resolve_review_task(case_id: str, body: ResolveBody):
    try:
        resolve_case(case_id, body.resolution, body.reviewer)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------

@app.get("/api/audit")
async def list_audit_events():
    events_path = project_root / "logs" / "events.jsonl"
    if not events_path.exists():
        return []
    events = []
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            mapped = _map_audit_event(line)
            if mapped:
                events.append(mapped)
    events.reverse()
    return events


# ---------------------------------------------------------------------------
# AI Agent chat endpoint
# ---------------------------------------------------------------------------

class _ChatMessage(BaseModel):
    role: str
    content: str

class _GeminiChatBody(BaseModel):
    messages: List[_ChatMessage]
    context: dict = {}


def _extract_job_params(text: str) -> dict:
    params: dict = {"title": "", "department": "Engineering", "location": "Remote", "must_have": [], "nice_to_have": []}
    title_m = re.search(
        r"(?:for (?:a|an) )([\w\s]+?)(?:\s+(?:role|position|job|engineer|developer|manager|analyst|designer|at|in|with|,|$))",
        text, re.IGNORECASE
    )
    if title_m:
        params["title"] = title_m.group(1).strip().title()
    else:
        role_m = re.search(
            r"([\w\s]+?)\s+(?:role|position|engineer|developer|manager|analyst|designer)\b",
            text, re.IGNORECASE
        )
        if role_m:
            params["title"] = role_m.group(0).strip().title()

    loc_m = re.search(r"(?:in|at|based in|located in)\s+([\w\s,]+?)(?:\s+with|\s+who|\s+and|,|\.|$)", text, re.IGNORECASE)
    if loc_m:
        params["location"] = loc_m.group(1).strip()

    known_skills = [
        "Python", "JavaScript", "TypeScript", "Java", "React", "Node.js", "AWS", "Go", "Rust",
        "SQL", "Kubernetes", "Docker", "FastAPI", "Django", "Vue", "Angular", "PostgreSQL",
        "MongoDB", "Machine Learning", "LLMs", "NLP", "GCP", "Azure", "C++", "C#",
    ]
    found = [s for s in known_skills if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]
    params["must_have"] = list(dict.fromkeys(found))
    return params


def _format_jobs_list(jobs: list, query: str = "") -> str:
    if not jobs:
        return "No job requirements are currently active in the system."
    q = query.lower()
    filtered = [
        j for j in jobs
        if not q or q in j.get("title", "").lower()
        or q in j.get("department", "").lower()
        or q in j.get("location", "").lower()
        or any(q in tag.lower() for tag in j.get("tags", []))
    ] or jobs
    lines = [f"Found **{len(filtered)} job(s)**:\n"]
    for j in filtered[:10]:
        lines.append(f"- **{j.get('title')}** — {j.get('department', '')} • {j.get('location', '')} `{j.get('status', 'MATCHING')}`")
    return "\n".join(lines)


@app.post("/api/gemini/chat")
async def gemini_chat(body: _GeminiChatBody):
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    context = body.context
    last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    lower_msg = last_user_msg.lower()

    candidates: list = context.get("candidates", [])
    jobs: list = context.get("jobs", [])
    review_tasks: list = context.get("reviewTasks", [])
    pending_count = sum(1 for t in review_tasks if t.get("status") == "pending")
    actions_taken: list[dict] = []

    create_intent = any(p in lower_msg for p in [
        "create job", "add job", "new job", "post job",
        "create a job", "add a job", "create a new job", "create a role", "add a role",
    ])
    search_intent = any(p in lower_msg for p in [
        "find job", "search job", "list job", "show job",
        "what jobs", "which jobs", "show me job", "find a job",
    ])

    response_text = ""

    from core.extract import _configure_genai, _lm_studio_available, _lm_studio_chat, MODEL_NAME
    use_lm_studio = _lm_studio_available()
    llm_ok = use_lm_studio or _configure_genai()

    if llm_ok:
        system_prompt = (
            f"You are the Bloodhound AI Copilot for a recruitment intelligence platform.\n\n"
            f"System status: {len(candidates)} candidates, {len(jobs)} jobs, {pending_count} pending compliance reviews.\n"
            f"Active jobs: {', '.join(j.get('title','') for j in jobs[:6]) or 'none'}.\n\n"
            f"Capabilities:\n"
            f"1. CREATE JOBS — if user wants to create/add a job, include this marker on its own line before your explanation:\n"
            f'   [ACTION:CREATE_JOB] {{"title":"...","department":"...","location":"...","must_have":["..."],"nice_to_have":["..."]}}\n'
            f"2. SEARCH JOBS — list matching jobs from the active list above.\n"
            f"3. GENERAL — answer questions about candidates, compliance, GDPR, outreach.\n\n"
            f"Be concise and professional."
        )

        try:
            if use_lm_studio:
                lm_messages = [{"role": "system", "content": system_prompt}]
                for msg in messages:
                    lm_messages.append({"role": msg["role"], "content": msg["content"]})
                response_text = _lm_studio_chat(lm_messages)
            else:
                import google.generativeai as genai_module
                history = []
                for msg in messages[:-1]:
                    history.append({"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]})
                model = genai_module.GenerativeModel(model_name=MODEL_NAME, system_instruction=system_prompt)
                chat_session = model.start_chat(history=history)
                resp = chat_session.send_message(last_user_msg)
                response_text = resp.text

            action_m = re.search(r'\[ACTION:CREATE_JOB\]\s*(\{[^\n]+\})', response_text)
            if action_m:
                try:
                    jp = json.loads(action_m.group(1))
                    job_body = JobCreate(
                        title=jp.get("title", "New Role"),
                        department=jp.get("department", "Engineering"),
                        location=jp.get("location", "Remote"),
                        must_have=jp.get("must_have", []),
                        nice_to_have=jp.get("nice_to_have", []),
                    )
                    created = await create_job(job_body)
                    actions_taken.append({"type": "job_created", "data": created})
                    response_text = re.sub(r'\[ACTION:CREATE_JOB\]\s*\{[^\n]+\}\n?', '', response_text).strip()
                except Exception:
                    pass

        except Exception as exc:
            err = str(exc)
            if any(k in err.lower() for k in ("429", "quota", "rate", "exhausted")):
                llm_ok = False
                response_text = ""
            else:
                response_text = f"Agent error: {exc}"

    if not response_text:
        if create_intent:
            params = _extract_job_params(last_user_msg)
            if params["title"]:
                job_body = JobCreate(
                    title=params["title"],
                    department=params["department"],
                    location=params["location"],
                    must_have=params["must_have"],
                    nice_to_have=params["nice_to_have"],
                )
                created = await create_job(job_body)
                actions_taken.append({"type": "job_created", "data": created})
                skills_str = ", ".join(params["must_have"]) if params["must_have"] else "to be defined"
                response_text = (
                    f"Job **{params['title']}** has been created and is now live in the Job Match Matrix.\n\n"
                    f"- **Location**: {params['location']}\n"
                    f"- **Department**: {params['department']}\n"
                    f"- **Required skills**: {skills_str}\n\n"
                    "The matching engine will begin scoring candidates automatically."
                )
            else:
                response_text = (
                    "I'd be happy to create a job! Please include the role details, for example:\n\n"
                    "_\"Create a job for a Senior Python Developer in London with FastAPI and Docker\"_\n\n"
                    "Or use the **Create New Job** button in the Job Match Matrix screen."
                )
        elif search_intent:
            response_text = _format_jobs_list(jobs, last_user_msg)
        elif any(p in lower_msg for p in ["candidate", "talent", "pool", "how many"]):
            response_text = (
                f"**Talent Pool Overview**\n\n"
                f"- Total candidates: **{len(candidates)}**\n"
                f"- Active jobs: **{len(jobs)}**\n"
                f"- Pending compliance reviews: **{pending_count}**\n\n"
                "Use the Candidate Pool screen for detailed filtering."
            )
        elif any(p in lower_msg for p in ["compliance", "gdpr", "pending", "review"]):
            pending_tasks = [t for t in review_tasks if t.get("status") == "pending"]
            if pending_tasks:
                lines = [f"**{len(pending_tasks)} pending compliance task(s):**\n"]
                for t in pending_tasks[:5]:
                    lines.append(f"- `{t.get('id','')[:8]}` — {t.get('type','UNKNOWN').replace('_',' ')}")
                response_text = "\n".join(lines)
            else:
                response_text = "No pending compliance tasks. The candidate pool is fully compliant."
        else:
            response_text = (
                f"I'm the **Bloodhound AI Copilot**. Here's what I can do:\n\n"
                f"- **Create jobs**: _\"Create a job for a Senior React Developer in Berlin\"_\n"
                f"- **Search jobs**: _\"Find all engineering roles\"_ or _\"Show remote jobs\"_\n"
                f"- **Pool overview**: _\"How many candidates do we have?\"_\n"
                f"- **Compliance**: _\"What GDPR tasks are pending?\"_\n\n"
                f"Current system: **{len(candidates)} candidates**, **{len(jobs)} jobs**, **{pending_count} pending reviews**."
            )

    return {"text": response_text, "actions": actions_taken}


# ---------------------------------------------------------------------------
# Serve built React SPA (production)
# ---------------------------------------------------------------------------

UI_DIST = project_root / "ui" / "dist"

if UI_DIST.exists():
    assets_dir = UI_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = UI_DIST / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="UI not built yet — run: cd ui && npm run build")
        return FileResponse(str(index))


def start_server():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8080, reload=True)


if __name__ == "__main__":
    start_server()
