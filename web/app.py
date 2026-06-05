import json
import hmac
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.store import load_record, save_record
from core.match import generate_shortlist
from core.config import (
    DATA_DIR,
    RECORDS_DIR,
    REQUIREMENTS_DIR,
    PROJECTS_DIR,
    RECORD_INDEX_PATH,
    INTAKE_DIR,
    PROVIDERS,
    get_provider_api_key_last4,
    has_provider_api_key,
    set_provider_api_key,
)
from core.ingest import ingest_file
from core.path_utils import resolve_json_path
from core.review import get_review_queue, resolve_case, has_open_cases, _clear_record_review_hold
from core.events import log_event
from core.security import anonymize_candidate_record
from core.schemas import CandidateRecord, Identity, Profile, Compliance, Scores
from core.time_utils import utc_now_iso

app = FastAPI(title="Linnify AI Talent Pool Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _configured_api_token() -> Optional[str]:
    return os.getenv("TALENT_POOL_API_TOKEN") or os.getenv("APP_API_TOKEN")


def _request_api_token(request: Request) -> Optional[str]:
    token = request.headers.get("x-api-token")
    if token:
        return token
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


@app.middleware("http")
async def require_api_token_when_configured(request: Request, call_next):
    configured = _configured_api_token()
    if configured and request.url.path.startswith("/api"):
        supplied = _request_api_token(request)
        if not supplied or not hmac.compare_digest(supplied, configured):
            return JSONResponse({"detail": "Invalid or missing API token"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------------------
# App config (config.json at project root)
# ---------------------------------------------------------------------------

CONFIG_PATH = project_root / "config.json"
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


_MAX_CV_UPLOAD_BYTES = _int_env("MAX_CV_UPLOAD_BYTES", 10 * 1024 * 1024)


async def _write_upload_with_limit(file: UploadFile, dest: Path, *, max_bytes: int = _MAX_CV_UPLOAD_BYTES) -> int:
    total = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                mb = max_bytes // 1024 // 1024
                raise HTTPException(status_code=413, detail=f"File too large. Max {mb} MB.")
            out.write(chunk)
    return total


class AppConfig(BaseModel):
    """Persisted app config (committed to config.json).

    Provider API keys live in .secrets.json (gitignored) and are never
    serialized here. Use AppConfigResponse / AppConfigUpdate for transport.
    """
    provider: str = Field(default="local")
    model: str = Field(default="local-model")
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    sovereign_cloud: bool = Field(default=True)
    use_local_llm: bool = Field(default=True)


class AppConfigResponse(AppConfig):
    """Read shape - exposes which provider keys are set and their last-4 only."""
    gemini_api_key_set: bool = False
    gemini_api_key_last4: Optional[str] = None
    openai_api_key_set: bool = False
    openai_api_key_last4: Optional[str] = None
    anthropic_api_key_set: bool = False
    anthropic_api_key_last4: Optional[str] = None
    huggingface_api_key_set: bool = False
    huggingface_api_key_last4: Optional[str] = None


class AppConfigUpdate(AppConfig):
    """Write shape - optional plaintext keys per provider.

    For each key field: None → leave as-is, "" → clear, other → save.
    """
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    huggingface_api_key: Optional[str] = None


def load_app_config() -> AppConfig:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig(**data)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return AppConfig()


def save_app_config(cfg: AppConfig) -> None:
    from filelock import FileLock
    lock = FileLock(f"{CONFIG_PATH}.lock")
    with lock:
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, indent=2)
        tmp.replace(CONFIG_PATH)


def _config_response() -> AppConfigResponse:
    base = load_app_config()
    return AppConfigResponse(
        **base.model_dump(),
        gemini_api_key_set=has_provider_api_key("gemini"),
        gemini_api_key_last4=get_provider_api_key_last4("gemini"),
        openai_api_key_set=has_provider_api_key("openai"),
        openai_api_key_last4=get_provider_api_key_last4("openai"),
        anthropic_api_key_set=has_provider_api_key("anthropic"),
        anthropic_api_key_last4=get_provider_api_key_last4("anthropic"),
        huggingface_api_key_set=has_provider_api_key("huggingface"),
        huggingface_api_key_last4=get_provider_api_key_last4("huggingface"),
    )


@app.get("/api/config", response_model=AppConfigResponse)
async def get_config():
    return _config_response()


@app.get("/api/lm-studio/status")
async def lm_studio_status():
    """Probe the local LM Studio server. Used by the Settings page to show a
    live green/red badge next to the 'Use Local LLM' toggle."""
    from core.extract import _lm_studio_available
    from core.config import LM_STUDIO_MODEL, LM_STUDIO_BASE_URL
    return {
        "available": _lm_studio_available(),
        "model": LM_STUDIO_MODEL,
        "base_url": LM_STUDIO_BASE_URL,
    }


@app.post("/api/config", response_model=AppConfigResponse)
async def post_config(body: AppConfigUpdate):
    key_fields = {"gemini_api_key", "openai_api_key", "anthropic_api_key", "huggingface_api_key"}
    cfg = AppConfig(**body.model_dump(exclude=key_fields))
    if cfg.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: '{cfg.provider}'")
    try:
        save_app_config(cfg)
        for provider, value in (
            ("gemini", body.gemini_api_key),
            ("openai", body.openai_api_key),
            ("anthropic", body.anthropic_api_key),
            ("huggingface", body.huggingface_api_key),
        ):
            if value is not None:
                set_provider_api_key(provider, value.strip() or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")
    return _config_response()


class LinkedInPreviewBody(BaseModel):
    linkedinUrl: str


class CVPreviewBody(BaseModel):
    resumeText: str


@app.post("/api/gemini/parse-cv")
async def parse_cv_preview(body: CVPreviewBody):
    text = body.resumeText.strip()
    if not text:
        raise HTTPException(status_code=400, detail="resumeText is required")

    try:
        from core.extract import extract_candidate_data
        extraction, _model_info = extract_candidate_data(text)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"CV parsing failed: {e}")

    return {
        "candidate": {
            "name": extraction.name or "Unknown",
            "seniority": extraction.seniority or "Unknown",
            "topSkills": [s.upper() for s in (extraction.technologies_used or [])[:5]],
            "matchScore": extraction.extraction_confidence,
            "complianceStatus": "PENDING REVIEW",
        }
    }


@app.post("/api/gemini/parse-linkedin")
async def parse_linkedin_profile(body: LinkedInPreviewBody):
    linkedin_url = _validate_linkedin_url(body.linkedinUrl)
    name = _linkedin_profile_name(linkedin_url)
    return {
        "candidate": {
            "name": name,
            "seniority": "LinkedIn profile",
            "topSkills": ["LINKEDIN"],
            "matchScore": 0.5,
            "complianceStatus": "PENDING REVIEW",
        }
    }


# ---------------------------------------------------------------------------
# Data mapping helpers
# ---------------------------------------------------------------------------

def _initials(name: Optional[str]) -> str:
    if not name:
        return "??"
    parts = name.strip().split()
    return "".join(p[0] for p in parts if p)[:2].upper()


def _linkedin_profile_name(linkedin_url: str) -> str:
    slug = linkedin_url.rstrip("/").split("/")[-1]
    words = [w for w in re.split(r"[-_.]+", slug) if w]
    return " ".join(word.capitalize() for word in words) or "LinkedIn Candidate"


def _validate_linkedin_url(linkedin_url: str) -> str:
    value = linkedin_url.strip()
    if not re.match(r"^https://(?:www\.)?linkedin\.com/in/[^/\s]+/?$", value):
        raise HTTPException(status_code=400, detail="linkedinUrl must be a https://linkedin.com/in/... profile URL")
    return value


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
        "matchScore": (
            rec.scores.last_match_score
            or rec.scores.identity_confidence
            or rec.scores.extraction_confidence
            or 0.0
        ),
        "complianceStatus": _compliance_status(rec),
        "linkedinUrl": rec.identity.linkedin_url or None,
        "location": rec.profile.location or None,
        "source": rec.compliance.source or "Unknown",
    }


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@app.get("/api/candidates")
async def list_candidates(search: Optional[str] = None):
    if not RECORDS_DIR.exists():
        return {"candidates": []}
    results = []
    for path in sorted(RECORDS_DIR.glob("*.json")):
        record_id = path.stem
        try:
            rec = load_record(record_id)
        except Exception:
            continue
        if rec.state and rec.state.archived:
            continue
        mapped = _map_candidate(record_id, rec)
        if search:
            q = search.lower()
            haystack = " ".join([
                mapped["name"],
                mapped["seniority"],
                " ".join(mapped["topSkills"]),
                mapped.get("location") or "",
            ]).lower()
            if q not in haystack:
                continue
        results.append(mapped)
    return {"candidates": results}


@app.get("/api/candidates/{record_id}")
async def get_candidate(record_id: str):
    try:
        rec = load_record(record_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _map_candidate(record_id, rec)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@app.post("/api/ingest/file")
async def ingest_file_upload(file: UploadFile = File(...)):
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    dest = INTAKE_DIR / file.filename
    await _write_upload_with_limit(file, dest)
    try:
        record_id = ingest_file(dest)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Ingest failed: {e}")
    return {"record_id": record_id, "status": "ingested"}


class IngestLinkedInBody(BaseModel):
    linkedinUrl: str
    consentGiven: bool = False


@app.post("/api/ingest/linkedin")
async def ingest_linkedin(body: IngestLinkedInBody):
    linkedin_url = _validate_linkedin_url(body.linkedinUrl)
    if not body.consentGiven:
        raise HTTPException(status_code=400, detail="Consent is required to ingest a LinkedIn profile")
    # Minimal stub record — real enrichment requires a scraper integration
    name = _linkedin_profile_name(linkedin_url)
    record_id = f"li-{uuid.uuid4().hex[:8]}"
    rec = CandidateRecord(
        identity=Identity(primary_name=name, linkedin_url=linkedin_url),
        profile=Profile(),
        compliance=Compliance(
            source="linkedin",
            consent_given=True,
            human_review_required=True,
        ),
        scores=Scores(),
    )
    save_record(record_id, rec)
    log_event("ingest", {"record_id": record_id, "source": "linkedin", "url": linkedin_url})
    return {"record_id": record_id, "status": "ingested"}


# ---------------------------------------------------------------------------
# Jobs (requirements)
# ---------------------------------------------------------------------------

class JobCreateBody(BaseModel):
    title: str
    description: Optional[str] = None
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    location: Optional[str] = None
    years_of_experience: Optional[int] = None
    language: List[str] = Field(default_factory=list)


def _load_req(req_id: str) -> dict:
    path = REQUIREMENTS_DIR / f"{req_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _map_job(req_id: str, data: dict) -> dict:
    crit = data.get("requirements") or {}
    shortlist = data.get("shortlist") or []
    return {
        "id": req_id,
        "title": data.get("title") or "Untitled",
        "description": data.get("description") or "",
        "status": data.get("status", "OPEN"),
        "createdAt": data.get("created_at") or "",
        "shortlistGeneratedAt": data.get("shortlist_generated_at") or None,
        "requirements": {
            "mustHave": crit.get("must_have") or [],
            "niceToHave": crit.get("nice_to_have") or [],
            "seniority": crit.get("seniority") or None,
            "location": crit.get("location") or None,
            "yearsOfExperience": crit.get("years_of_experience") or None,
            "language": crit.get("language") or [],
        },
        "shortlist": shortlist,
    }


@app.get("/api/jobs")
async def list_jobs(search: Optional[str] = None):
    if not REQUIREMENTS_DIR.exists():
        return {"jobs": []}
    jobs = []
    for path in sorted(REQUIREMENTS_DIR.glob("*.json")):
        req_id = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        mapped = _map_job(req_id, data)
        if search:
            q = search.lower()
            if q not in mapped["title"].lower() and q not in (mapped["description"] or "").lower():
                continue
        jobs.append(mapped)
    return {"jobs": jobs}


@app.post("/api/jobs")
async def create_job(body: JobCreateBody):
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    req_id = f"req-{uuid.uuid4().hex[:8]}"
    data = {
        "id": req_id,
        "title": body.title,
        "description": body.description or "",
        "status": "OPEN",
        "created_at": utc_now_iso(),
        "requirements": {
            "must_have": body.must_have,
            "nice_to_have": body.nice_to_have,
            "seniority": body.seniority,
            "location": body.location,
            "years_of_experience": body.years_of_experience,
            "language": body.language,
        },
        "shortlist": [],
    }
    path = REQUIREMENTS_DIR / f"{req_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log_event("job_created", {"req_id": req_id, "title": body.title})
    return _map_job(req_id, data)


@app.get("/api/jobs/{req_id}")
async def get_job(req_id: str):
    return _map_job(req_id, _load_req(req_id))


@app.post("/api/jobs/{req_id}/shortlist")
async def run_shortlist(req_id: str, top_n: int = 5):
    _load_req(req_id)  # 404 guard
    try:
        result = generate_shortlist(req_id, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {e}")
    log_event("shortlist_generated", {"req_id": req_id, "results": len(result.get("results", []))})
    return result


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreateBody(BaseModel):
    title: str
    brief: Optional[str] = None
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    location: Optional[str] = None
    years_of_experience: Optional[int] = None
    language: List[str] = Field(default_factory=list)


def _load_project(project_id: str) -> dict:
    path = PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _map_project(project_id: str, data: dict) -> dict:
    crit = data.get("requirements") or {}
    return {
        "id": project_id,
        "title": data.get("title") or "Untitled",
        "brief": data.get("brief") or "",
        "status": data.get("status", "OPEN"),
        "createdAt": data.get("created_at") or "",
        "matchGeneratedAt": data.get("match_generated_at") or None,
        "requirements": {
            "mustHave": crit.get("must_have") or [],
            "niceToHave": crit.get("nice_to_have") or [],
            "seniority": crit.get("seniority") or None,
            "location": crit.get("location") or None,
            "yearsOfExperience": crit.get("years_of_experience") or None,
            "language": crit.get("language") or [],
        },
        "matches": data.get("matches") or [],
    }


@app.get("/api/projects")
async def list_projects(search: Optional[str] = None):
    """Return all projects, optionally filtered by title/brief."""
    if not PROJECTS_DIR.exists():
        return {"projects": []}
    projects = []
    for path in sorted(PROJECTS_DIR.glob("*.json")):
        project_id = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        mapped = _map_project(project_id, data)
        if search:
            q = search.lower()
            if q not in mapped["title"].lower() and q not in (mapped["brief"] or "").lower():
                continue
        projects.append(mapped)
    return {"projects": projects}


@app.post("/api/projects", status_code=201)
async def create_project(body: ProjectCreateBody):
    """Create a new project and persist it to data/projects/."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    data = {
        "id": project_id,
        "title": body.title,
        "brief": body.brief or "",
        "status": "OPEN",
        "created_at": utc_now_iso(),
        "requirements": {
            "must_have": body.must_have,
            "nice_to_have": body.nice_to_have,
            "seniority": body.seniority,
            "location": body.location,
            "years_of_experience": body.years_of_experience,
            "language": body.language,
        },
        "matches": [],
    }
    path = PROJECTS_DIR / f"{project_id}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log_event("project_created", {"project_id": project_id, "title": body.title})
    return _map_project(project_id, data)


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Return a single project by ID, including its cached matches."""
    return _map_project(project_id, _load_project(project_id))


@app.post("/api/projects/{project_id}/match")
async def run_project_match(project_id: str, top_n: int = 5):
    """Run the full matching pipeline against the project's requirements.

    The project's requirements are written as a temporary RequirementRecord
    into REQUIREMENTS_DIR so the existing ``generate_shortlist`` pipeline
    can process them without modification.  The temp file is cleaned up
    after the run regardless of outcome.
    """
    data = _load_project(project_id)  # 404 guard

    # Write a temporary requirement file reusing the project's criteria.
    tmp_req_id = f"_proj_tmp_{project_id}"
    tmp_path = REQUIREMENTS_DIR / f"{tmp_req_id}.json"
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    req_data = {
        "id": tmp_req_id,
        "title": data.get("title", ""),
        "description": data.get("brief", ""),
        "requirements": data.get("requirements") or {},
    }
    tmp_path.write_text(json.dumps(req_data, indent=2), encoding="utf-8")

    try:
        result = generate_shortlist(tmp_req_id, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Persist matches back into the project file.
    data["matches"] = result.get("results", [])
    data["match_generated_at"] = utc_now_iso()
    project_path = PROJECTS_DIR / f"{project_id}.json"
    project_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    log_event("project_match_run", {
        "project_id": project_id,
        "total_evaluated": result.get("total_candidates_evaluated", 0),
        "matches": len(data["matches"]),
    })
    return {
        "project_id": project_id,
        "total_candidates_evaluated": result.get("total_candidates_evaluated", 0),
        "funnel_size": result.get("funnel_size", 0),
        "matches": data["matches"],
    }


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@app.get("/api/review")
async def list_review_tasks(status: Optional[str] = None):
    queue = get_review_queue()
    if status:
        queue = [t for t in queue if t.get("status", "").upper() == status.upper()]
    return {"tasks": queue}


class ResolveBody(BaseModel):
    decision: str  # "approve" | "reject" | "purge"
    reason: Optional[str] = None


@app.post("/api/review/{case_id}/resolve")
async def resolve_review_case(case_id: str, body: ResolveBody):
    allowed = {"approve", "reject", "purge"}
    decision = body.decision.lower()
    if decision not in allowed:
        raise HTTPException(status_code=400, detail=f"decision must be one of {allowed}")
    try:
        resolve_case(case_id, decision, reason=body.reason)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Review case not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not resolve case: {e}")
    log_event("review_resolved", {"case_id": case_id, "decision": decision})
    return {"case_id": case_id, "decision": decision, "status": "resolved"}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@app.get("/api/audit")
async def get_audit_log(limit: int = 100):
    from core.config import EVENTS_LOG_PATH
    if not EVENTS_LOG_PATH.exists():
        return {"events": []}
    lines = EVENTS_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    events = []
    for line in reversed(lines[-limit:]):
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return {"events": events}


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

@app.post("/api/maintenance/archive-stale")
async def archive_stale_candidates():
    from core.config import STALE_REFRESH_MONTHS
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_REFRESH_MONTHS * 30)
    archived = []
    if not RECORDS_DIR.exists():
        return {"archived": archived}
    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            rec = load_record(record_id)
        except Exception:
            continue
        if rec.state and rec.state.archived:
            continue
        ingested_at = getattr(rec.compliance, "ingested_at", None)
        if ingested_at:
            try:
                ts = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
                if ts < cutoff:
                    if rec.state is None:
                        from core.schemas import State
                        rec = rec.model_copy(update={"state": State(archived=True)})
                    else:
                        rec.state.archived = True
                    save_record(record_id, rec)
                    archived.append(record_id)
            except Exception:
                continue
    log_event("maintenance_archive_stale", {"archived_count": len(archived)})
    return {"archived": archived}


@app.post("/api/maintenance/cleanup-review")
async def cleanup_completed_review_tasks():
    """Remove resolved/rejected/purged review cases older than 30 days."""
    from core.review import _review_dir
    cleaned = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    review_dir = _review_dir()
    if not review_dir.exists():
        return {"cleaned": cleaned}
    for path in review_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = data.get("status", "").lower()
            if status not in ("resolved", "rejected", "purged", "approved"):
                continue
            resolved_at = data.get("resolved_at") or data.get("updated_at") or ""
            if resolved_at:
                ts = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
                if ts < cutoff:
                    path.unlink(missing_ok=True)
                    cleaned.append(path.stem)
        except Exception:
            continue
    log_event("maintenance_cleanup_review", {"cleaned_count": len(cleaned)})
    return {"cleaned": cleaned}


# ---------------------------------------------------------------------------
# Stats (used by Overview + Settings pages)
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats():
    candidates_count = len(list(RECORDS_DIR.glob("*.json"))) if RECORDS_DIR.exists() else 0
    jobs_count = len(list(REQUIREMENTS_DIR.glob("*.json"))) if REQUIREMENTS_DIR.exists() else 0
    projects_count = len(list(PROJECTS_DIR.glob("*.json"))) if PROJECTS_DIR.exists() else 0
    review_queue = get_review_queue()
    pending_reviews = sum(1 for t in review_queue if t.get("status", "").upper() == "PENDING")
    return {
        "candidatesCount": candidates_count,
        "jobsCount": jobs_count,
        "projectsCount": projects_count,
        "pendingReviewsCount": pending_reviews,
        "tasksCount": len(review_queue),
    }


# ---------------------------------------------------------------------------
# SPA catch-all (must be last)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "dist"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {"message": "API running. Build the frontend with: cd web && npm run build"}
