import json
import uuid
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.store import load_record
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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def _map_review_task(case: dict) -> dict:
    reason = case.get("reason", "")
    if "identity" in reason:
        task_type = "IDENTITY_CONFLICT"
    elif any(k in reason for k in ("pii", "consent", "compliance", "retention", "gdpr")):
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

    # Attach nested detail objects so the UI can render them
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
            "subject": f"Opportunity at Bloodhound for {name}",
            "draftBody": case.get("draft_body", ""),
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
    if not RECORD_INDEX_PATH.exists():
        return candidates
    try:
        with open(RECORD_INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
    except (json.JSONDecodeError, OSError):
        return candidates
    for record_id in index:
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
        "department": data.get("description", ""),
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
            raise HTTPException(status_code=404, detail="UI not built yet")
        return FileResponse(str(index))


def start_server():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8080, reload=True)


if __name__ == "__main__":
    start_server()
