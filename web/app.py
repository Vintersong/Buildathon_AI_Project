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
        "actionsRequired": rec.compliance.human_review_required,
    }


def _map_candidate_detail(record_id: str, rec) -> dict:
    """Extended mapping exposing all extracted profile fields for the detail drawer."""
    base = _map_candidate(record_id, rec)
    base.update({
        "headline": rec.profile.headline or "",
        "summary": rec.profile.summary or "",
        "location": rec.profile.location or "",
        "yearsOfExperience": rec.profile.years_of_experience,
        "studyDegrees": rec.profile.study_degrees or [],
        "languagesSpoken": rec.profile.languages_spoken or [],
        "previousJobs": rec.profile.previous_jobs or [],
        "projectsDeveloped": rec.profile.projects_developed or [],
        "allSkills": [s.upper() for s in (rec.profile.technologies_used or [])],
        "linkedinUrl": rec.identity.linkedin_url or "",
        "emails": rec.identity.emails or [],
        "consentBasis": rec.compliance.consent_basis or "",
        "dataRegion": rec.compliance.data_region or "EEA",
        "retentionUntil": rec.compliance.retention_until or "",
        "extractionConfidence": rec.scores.extraction_confidence,
        "lastMatchScore": rec.scores.last_match_score,
        "updatedAt": rec.updated_at,
        "createdAt": rec.created_at,
    })
    return base


def _map_candidate_agent_context(record_id: str, rec) -> dict:
    """PII-minimized candidate context for hosted/local chat prompts."""
    anonymized = anonymize_candidate_record(rec, record_id)
    return {
        "id": record_id,
        "profile": anonymized.anonymized_text,
        "complianceStatus": _compliance_status(rec),
        "reviewRequired": rec.compliance.human_review_required,
        "extractionConfidence": rec.scores.extraction_confidence,
        "lastMatchScore": rec.scores.last_match_score,
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


def _outreach_signals(rec) -> list[str]:
    """Derive personalization trigger signals from a candidate record."""
    signals = []
    if rec.profile.technologies_used:
        top = rec.profile.technologies_used[:3]
        signals.append(f"Tech match: {', '.join(top)}")
    if rec.profile.years_of_experience:
        signals.append(f"{rec.profile.years_of_experience} yrs experience")
    if rec.profile.location:
        signals.append(f"Location: {rec.profile.location}")
    if rec.profile.seniority:
        signals.append(f"Seniority: {rec.profile.seniority}")
    if rec.profile.study_degrees:
        signals.append(f"Degree: {rec.profile.study_degrees[0]}")
    if rec.profile.languages_spoken:
        signals.append(f"Languages: {', '.join(rec.profile.languages_spoken[:2])}")
    return signals or ["Profile extracted from CV"]


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
    created_at = case.get("created_at", utc_now_iso())

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
        signals = _outreach_signals(rec) if rec else ["Profile extracted from CV"]
        task["outreachDetails"] = {
            "targetName": name,
            "subject": f"Opportunity for {name}",
            "draftBody": case.get("draft_text") or case.get("draft_body", ""),
            "signals": signals,
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
        task["proposedRecord"] = {
            "source": case.get("source", "new_ingest"),
            "name": case.get("proposed_name") or name,
            "currentRole": case.get("proposed_role") or (rec.profile.headline if rec else ""),
            "location": case.get("proposed_location") or (rec.profile.location if rec else ""),
            "linkedin": case.get("proposed_linkedin") or (rec.identity.linkedin_url if rec else ""),
            "addedRole": case.get("added_role") or "",
            "removedRole": case.get("removed_role") or "",
        }
        task["recommendation"] = case.get("recommendation") or reason

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


@app.get("/api/candidates/{record_id}")
async def get_candidate(record_id: str):
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")
    return _map_candidate_detail(record_id, rec)


@app.post("/api/intake/process")
async def process_intake(limit: int = 25):
    """
    Walk intake/cvs/ and ingest every .pdf / .txt that isn't already in the
    manifest. Capped by `limit` (default 25) to protect API quotas; raise it
    explicitly when you know you have headroom.

    Returns {processed, skipped, failed, errors, total_intake, attempted}.
    """
    cvs_dir = INTAKE_DIR / "cvs"
    if not cvs_dir.exists():
        return {"processed": 0, "skipped": 0, "failed": 0, "errors": [], "total_intake": 0, "attempted": 0}

    candidates = sorted(
        p for p in cvs_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".pdf", ".txt")
    )
    total = len(candidates)
    limit = max(1, min(limit, 500))  # hard cap to prevent runaway

    processed, skipped, failed = 0, 0, 0
    errors: list[dict] = []

    for path in candidates[:limit]:
        try:
            result = ingest_file(path)
            if result.get("status") == "skipped":
                skipped += 1
            else:
                processed += 1
        except Exception as e:
            failed += 1
            errors.append({"file": path.name, "error": str(e)[:200]})

    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:10],  # cap to keep response small
        "total_intake": total,
        "attempted": min(limit, total),
    }


@app.post("/api/candidates/ingest")
async def ingest_candidate(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported")

    cvs_dir = INTAKE_DIR / "cvs"
    cvs_dir.mkdir(parents=True, exist_ok=True)

    dest = cvs_dir / f"upload_{uuid.uuid4().hex[:8]}{suffix}"
    try:
        await _write_upload_with_limit(file, dest)
        result = ingest_file(dest)
        record_id = result["record_id"]
    except Exception as e:
        dest.unlink(missing_ok=True)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))

    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=500, detail="Record not found after ingest")
    return _map_candidate(record_id, rec)


class LinkedInReingestBody(BaseModel):
    linkedinUrl: str


@app.post("/api/candidates/ingest/linkedin")
async def ingest_linkedin_candidate(body: LinkedInReingestBody):
    linkedin_url = _validate_linkedin_url(body.linkedinUrl)
    now = utc_now_iso()
    record_id = f"cand_{uuid.uuid4().hex[:12]}"
    name = _linkedin_profile_name(linkedin_url)

    rec = CandidateRecord(
        created_at=now,
        updated_at=now,
        identity=Identity(primary_name=name, linkedin_url=linkedin_url),
        profile=Profile(
            headline="LinkedIn profile import",
            summary=f"Profile imported from {linkedin_url}",
            seniority="Unknown",
        ),
        scores=Scores(extraction_confidence=0.5),
        compliance=Compliance(
            consent_basis="legitimate_interest",
            source="linkedin",
            human_review_required=True,
        ),
    )

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "linkedin_profile_ingested",
        "timestamp": now,
        "actor": {"type": "human"},
        "source": {"record_id": record_id, "source_type": "linkedin_ingest", "linkedin_url": linkedin_url},
        "changes": [{"operation": "create", "path": "/", "value": "linkedin_profile"}],
        "review": {"required": True, "reason": "linkedin_profile_review"},
        "confidence": 0.5,
    }

    try:
        save_record(record_id, rec, event=event)
        from core.review import add_to_queue
        add_to_queue([{
            "case_id": f"review_{uuid.uuid4().hex[:12]}",
            "record_id": record_id,
            "reason": "linkedin_profile_review",
            "created_at": now,
            "status": "open",
        }])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest LinkedIn profile: {e}")

    return _map_candidate(record_id, rec)


@app.post("/api/candidates/{record_id}/reingest")
async def reingest_candidate(
    record_id: str,
    file: UploadFile = File(...),
):
    """
    Re-ingest an existing candidate with a new CV file (multipart/form-data, field: file).
    For LinkedIn URL updates use POST /api/candidates/:id/reingest/linkedin.
    """
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported")

    cvs_dir = INTAKE_DIR / "cvs"
    cvs_dir.mkdir(parents=True, exist_ok=True)
    dest = cvs_dir / f"reingest_{record_id}_{uuid.uuid4().hex[:6]}{suffix}"
    try:
        await _write_upload_with_limit(file, dest)
        ingest_file(dest, force=True, target_record_id=record_id)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except PermissionError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    updated = load_record(record_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Record not found after re-ingest")
    return _map_candidate(record_id, updated)


@app.post("/api/candidates/{record_id}/reingest/linkedin")
async def reingest_candidate_linkedin(record_id: str, body: LinkedInReingestBody):
    """
    Update a candidate's stored LinkedIn URL and emit a provenance audit event.
    Separate route to avoid multipart/JSON body mixing issues in FastAPI.
    """
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    linkedin_url = _validate_linkedin_url(body.linkedinUrl)

    now = utc_now_iso()
    old_url = rec.identity.linkedin_url or ""
    rec.identity.linkedin_url = linkedin_url
    rec.updated_at = now

    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "linkedin_url_updated",
        "timestamp": now,
        "actor": {"type": "human"},
        "source": {"record_id": record_id, "source_type": "linkedin_reingest"},
        "changes": [{
            "operation": "replace",
            "path": "/identity/linkedin_url",
            "old_value": old_url,
            "new_value": linkedin_url,
        }],
        "confidence": 1.0,
    }

    try:
        save_record(record_id, rec, event=event)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist record: {e}")

    return _map_candidate(record_id, rec)


class StatusPatch(BaseModel):
    complianceStatus: str


@app.patch("/api/candidates/{record_id}/status")
async def patch_candidate_status(record_id: str, body: StatusPatch):
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found")

    status = body.complianceStatus.upper().strip()

    queued_case_id: Optional[str] = None
    if status == "COMPLIANT":
        rec.compliance.human_review_required = False
        # Also clear a near-expiry retention date so `_compliance_status()`
        # actually returns COMPLIANT. Without this, marking an EXPIRING
        # candidate compliant silently reverts on the next read because
        # retention_until is still within the 14-day window.
        rec.compliance.retention_until = None
    elif status == "PENDING REVIEW":
        rec.compliance.human_review_required = True
        # Also enqueue a review case so the candidate actually appears in the
        # review queue. Without this, the flag is set but no task exists, and
        # the RESOLVE button on the candidate row has nothing to open.
        if not has_open_cases(record_id):
            from core.review import add_to_queue
            queued_case_id = f"review_{uuid.uuid4().hex[:12]}"
            add_to_queue([{
                "case_id": queued_case_id,
                "record_id": record_id,
                "reason": "manual_review_requested",
                "created_at": utc_now_iso(),
                "status": "open",
            }])
    elif status in ("EXPIRING (14D)", "EXPIRING"):
        rec.compliance.retention_until = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown complianceStatus: '{body.complianceStatus}'")

    rec.updated_at = utc_now_iso()

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
    # Read persisted shortlist if available
    raw_shortlist = data.get("shortlist", [])
    shortlist = []
    for item in raw_shortlist:
        rec = load_record(item.get("record_id", ""))
        name = rec.identity.primary_name if rec else item.get("candidate_name", "")
        shortlist.append({
            "id": item.get("record_id", ""),
            "name": name,
            "confidence": item.get("match_score", 0.0),
            "explanation": "; ".join(item.get("evidence", [])),
            "status": "pending_review" if item.get("review_required") else "active",
            "initials": _initials(name),
        })
    return {
        "id": req_id,
        "title": data.get("title", ""),
        "department": data.get("department") or data.get("description", ""),
        "location": reqs.get("location", ""),
        "status": data.get("status", "MATCHING"),
        "tags": data.get("tags") or reqs.get("must_have", [])[:2],
        "candidatesProcessed": data.get("shortlist_meta", {}).get("total_filtered", 0),
        "shortlist": shortlist,
    }


@app.post("/api/candidates/{record_id}/clear-review-flag")
async def clear_candidate_review_flag(record_id: str):
    """
    Reconcile orphaned PENDING REVIEW state: clear human_review_required when
    no open review cases reference the candidate. Used by the UI RESOLVE button
    when the resolved-on-disk cases left the candidate flag stuck on.
    """
    rec = load_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if has_open_cases(record_id):
        raise HTTPException(
            status_code=409,
            detail="Open review cases exist for this candidate. Resolve them via the review queue.",
        )
    if rec.compliance.human_review_required:
        _clear_record_review_hold(record_id, reviewer="ui_manual_reconcile")
        rec = load_record(record_id)
    return _map_candidate(record_id, rec)


@app.delete("/api/jobs/{req_id}")
async def delete_job(req_id: str):
    try:
        path = resolve_json_path(REQUIREMENTS_DIR, req_id, kind="job")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        path.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {e}")
    return {"deleted": req_id}


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
    now = utc_now_iso()
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
        "shortlist": [],
        "shortlist_meta": {},
        "status": body.status,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
    }
    REQUIREMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = resolve_json_path(REQUIREMENTS_DIR, req_id, kind="job")
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
    for item in result.get("results", []):
        rec_id = item.get("record_id", "")
        name = item.get("name") or rec_id
        confidence = item.get("llm_score", item.get("combined_score", 0.0))
        shortlist.append({
            "id": rec_id,
            "name": name,
            "confidence": confidence,
            "explanation": "; ".join(item.get("evidence", [])),
            "status": "active",
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
        resolve_case(case_id, resolved_by=body.reviewer, resolution=body.resolution)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True}


class OutreachDraftBody(BaseModel):
    candidateId: str
    jobId: str
    candidateName: str
    jobTitle: str


@app.post("/api/review/outreach-draft")
async def create_outreach_draft(body: OutreachDraftBody):
    """
    Ask the agent to generate a personalised outreach email for a shortlisted
    candidate + job pairing.  Creates an OUTREACH_DRAFT ReviewTask and returns
    it immediately so the UI can open it in the ReviewQueue without a reload.
    """
    from core.outreach import generate_draft

    existing_cases = get_review_queue()
    for case in existing_cases:
        if (
            case.get("record_id") == body.candidateId
            and case.get("job_id") == body.jobId
            and "outreach" in case.get("reason", "")
            and case.get("status") == "open"
        ):
            return _map_review_task(case)

    try:
        case_id = generate_draft(body.candidateId, body.jobId)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Outreach generation failed: {e}")

    all_cases = get_review_queue()
    new_case = next((c for c in all_cases if c.get("case_id") == case_id), None)
    if not new_case:
        raise HTTPException(status_code=500, detail="Case created but not found in queue")

    return _map_review_task(new_case)


# ---------------------------------------------------------------------------
# Candidate maintenance endpoints
# ---------------------------------------------------------------------------

class BulkRefreshBody(BaseModel):
    ids: List[str]


async def _bulk_refresh_candidates(body: BulkRefreshBody):
    from core.maintenance import bulk_refresh

    updates = []
    missing = []
    for record_id in body.ids:
        rec = load_record(record_id)
        if not rec:
            missing.append(record_id)
            continue
        raw_text = "\n".join([
            rec.identity.primary_name or "",
            rec.profile.headline or rec.profile.seniority or "",
            rec.profile.summary or "",
            rec.identity.linkedin_url or "",
            "Skills: " + ", ".join(rec.profile.technologies_used or []),
            "Jobs: " + ", ".join(rec.profile.previous_jobs or []),
        ])
        updates.append({"record_id": record_id, "raw_text": raw_text})

    result = bulk_refresh(updates) if updates else {"success": 0, "failed": 0, "errors": []}
    if missing:
        result["failed"] = result.get("failed", 0) + len(missing)
        result.setdefault("errors", []).extend({"record_id": rid, "error": "Record not found"} for rid in missing)
    return result


@app.post("/api/candidates/bulk-refresh")
async def bulk_refresh_candidates(body: BulkRefreshBody):
    return await _bulk_refresh_candidates(body)


@app.post("/api/maintenance/bulk-refresh")
async def maintenance_bulk_refresh_candidates(body: BulkRefreshBody):
    return await _bulk_refresh_candidates(body)


@app.get("/api/maintenance/stale")
async def list_stale_candidates(months: int = 6):
    from core.maintenance import find_stale_candidates

    months = max(1, min(months, 60))
    stale = []
    for record_id in find_stale_candidates(months):
        rec = load_record(record_id)
        if rec and not rec.state.archived:
            item = _map_candidate(record_id, rec)
            item.update({
                "lastRefreshedAt": rec.state.last_refreshed_at or "",
                "updatedAt": rec.updated_at,
                "linkedinUrl": rec.identity.linkedin_url or "",
            })
            stale.append(item)
    return {"months": months, "candidates": stale}


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------

@app.get("/api/audit")
async def list_audit_events():
    from core.config import EVENTS_LOG_PATH
    events_path = EVENTS_LOG_PATH
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

class AgentActionResult(BaseModel):
    type: str
    data: Any = None

class AgentProposal(BaseModel):
    id: str
    type: str
    label: str
    description: str
    params: dict
    impact: str
    requiresConfirmation: bool = True
    createdAt: str

class AgentChatResponse(BaseModel):
    text: str
    actions: List[AgentActionResult] = Field(default_factory=list)
    proposals: List[AgentProposal] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

class AgentCreateJobParams(JobCreate):
    pass

class AgentShortlistParams(BaseModel):
    req_id: str
    top_n: int = Field(default=5, ge=1, le=25)

class AgentOutreachDraftParams(BaseModel):
    candidate_id: str
    job_id: str
    candidate_name: str = ""
    job_title: str = ""

class AgentResolveReviewParams(BaseModel):
    case_id: str
    resolution: str = "approved"

class AgentBulkRefreshParams(BaseModel):
    ids: List[str] = Field(default_factory=list)

class AgentProcessIntakeParams(BaseModel):
    limit: int = Field(default=25, ge=1, le=500)

AGENT_PROPOSALS_DIR = DATA_DIR / "agent_proposals"
_AGENT_PROPOSALS: dict[str, dict] = {}


def _dump_model(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _agent_proposal_path(proposal_id: str) -> Path:
    return resolve_json_path(AGENT_PROPOSALS_DIR, proposal_id, kind="agent proposal")


def _save_agent_proposal(proposal: dict) -> None:
    AGENT_PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    path = _agent_proposal_path(proposal.get("id", ""))
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2)
    tmp.replace(path)


def _consume_agent_proposal(proposal_id: str) -> Optional[dict]:
    try:
        path = _agent_proposal_path(proposal_id)
    except ValueError:
        raise

    proposal = _AGENT_PROPOSALS.pop(proposal_id, None)
    if proposal is None and path.exists():
        with open(path, "r", encoding="utf-8") as f:
            proposal = json.load(f)

    if proposal is not None:
        path.unlink(missing_ok=True)
    return proposal


def _agent_event(event_type: str, *, proposal: dict, actor: str = "system", result: Any = None, error: str = "") -> None:
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": event_type,
        "timestamp": utc_now_iso(),
        "actor": {"type": actor},
        "source": {
            "source_type": "agent",
            "proposal_id": proposal.get("id", ""),
            "action_type": proposal.get("type", ""),
        },
        "changes": [{"operation": event_type, "path": "/agent/proposals", "value": proposal.get("type", "")}],
        "agent": {
            "proposal_id": proposal.get("id", ""),
            "action_type": proposal.get("type", ""),
            "params": proposal.get("params", {}),
            "result": result,
            "error": error,
        },
        "confidence": 1.0,
    }
    try:
        log_event(event)
    except OSError as exc:
        print(f"[agent] audit log unavailable: {exc}")


def _agent_proposal(action_type: str, label: str, description: str, params: BaseModel, impact: str) -> AgentProposal:
    proposal = AgentProposal(
        id=f"agent_{uuid.uuid4().hex[:12]}",
        type=action_type,
        label=label,
        description=description,
        params=_dump_model(params),
        impact=impact,
        createdAt=utc_now_iso(),
    )
    stored = _dump_model(proposal)
    _AGENT_PROPOSALS[proposal.id] = stored
    _save_agent_proposal(stored)
    _agent_event("agent_action_proposed", proposal=stored)
    return proposal


def _job_label(job: dict) -> str:
    return f"{job.get('title', 'Untitled job')} ({job.get('location') or 'No location'})"


def _find_job_from_text(text: str, jobs: list) -> Optional[dict]:
    id_m = re.search(r"\breq_[A-Za-z0-9_-]+\b", text)
    if id_m:
        return next((j for j in jobs if j.get("id") == id_m.group(0)), None)

    lower = text.lower()
    exact = [j for j in jobs if j.get("title", "").lower() and j.get("title", "").lower() in lower]
    if exact:
        return sorted(exact, key=lambda j: len(j.get("title", "")), reverse=True)[0]

    tokens = {tok for tok in re.findall(r"[a-z0-9+#.]+", lower) if len(tok) > 2}
    scored = []
    for job in jobs:
        haystack = " ".join([
            job.get("title", ""),
            job.get("department", ""),
            job.get("location", ""),
            " ".join(job.get("tags", [])),
        ]).lower()
        score = sum(1 for tok in tokens if tok in haystack)
        if score:
            scored.append((score, job))
    if scored:
        scored.sort(key=lambda row: row[0], reverse=True)
        return scored[0][1]
    return jobs[0] if len(jobs) == 1 else None


def _find_candidate_from_text(text: str, candidates: list, jobs: list, job: Optional[dict] = None) -> Optional[dict]:
    id_m = re.search(r"\bcand_[A-Za-z0-9_-]+\b", text)
    if id_m:
        return next((c for c in candidates if c.get("id") == id_m.group(0)), None)

    lower = text.lower()
    exact = [c for c in candidates if c.get("name", "").lower() and c.get("name", "").lower() in lower]
    if exact:
        return sorted(exact, key=lambda c: len(c.get("name", "")), reverse=True)[0]

    if job:
        shortlist = job.get("shortlist") or []
        if shortlist:
            top = shortlist[0]
            return {"id": top.get("id"), "name": top.get("name") or top.get("id", "")}

    for existing_job in jobs:
        shortlist = existing_job.get("shortlist") or []
        if shortlist:
            top = shortlist[0]
            return {"id": top.get("id"), "name": top.get("name") or top.get("id", "")}
    return candidates[0] if len(candidates) == 1 else None


def _find_review_task_from_text(text: str, review_tasks: list) -> Optional[dict]:
    id_m = re.search(r"\breview_[A-Za-z0-9_-]+\b", text)
    if id_m:
        return next((t for t in review_tasks if t.get("id") == id_m.group(0)), None)

    pending = [t for t in review_tasks if t.get("status") == "pending"]
    lower = text.lower()
    for task in pending:
        if task.get("title", "").lower() and task.get("title", "").lower() in lower:
            return task
        details = task.get("complianceDetails") or task.get("outreachDetails") or {}
        for value in details.values():
            if isinstance(value, str) and value.lower() and value.lower() in lower:
                return task
    return pending[0] if len(pending) == 1 else None


def _resolution_from_text(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("purge", "delete", "remove", "gdpr erase", "erase")):
        return "purged"
    if any(word in lower for word in ("reject", "decline", "deny")):
        return "rejected"
    return "approved"


def _candidate_ids_from_text(text: str, candidates: list) -> list[str]:
    ids = list(dict.fromkeys(re.findall(r"\bcand_[A-Za-z0-9_-]+\b", text)))
    lower = text.lower()
    for candidate in candidates:
        name = candidate.get("name", "")
        if name and name.lower() in lower:
            ids.append(candidate.get("id", ""))
    return [cid for cid in dict.fromkeys(ids) if cid]


async def _execute_agent_proposal(proposal: dict) -> AgentActionResult:
    action_type = proposal.get("type", "")
    params = proposal.get("params", {})

    async def with_heuristic_extraction(operation):
        from core import extract

        previous = extract.ENABLE_EXTERNAL_LLM
        extract.ENABLE_EXTERNAL_LLM = False
        try:
            return await operation()
        finally:
            extract.ENABLE_EXTERNAL_LLM = previous

    if action_type == "CREATE_JOB":
        body = AgentCreateJobParams(**params)
        data = await create_job(JobCreate(**_dump_model(body)))
        return AgentActionResult(type="job_created", data=data)

    if action_type == "RUN_SHORTLIST":
        body = AgentShortlistParams(**params)
        result = generate_shortlist(body.req_id, top_n=body.top_n, use_llm_rerank=False)
        data = []
        for item in result.get("results", []):
            rec_id = item.get("record_id", "")
            name = item.get("name") or rec_id
            confidence = item.get("combined_score", item.get("llm_score", 0.0))
            data.append({
                "id": rec_id,
                "name": name,
                "confidence": confidence,
                "explanation": "; ".join(item.get("evidence", [])),
                "status": "active",
                "initials": _initials(name),
            })
        return AgentActionResult(type="shortlist_generated", data={"req_id": body.req_id, "shortlist": data})

    if action_type == "CREATE_OUTREACH_DRAFT":
        body = AgentOutreachDraftParams(**params)
        from core import outreach

        previous = outreach.ENABLE_EXTERNAL_OUTREACH_LLM
        outreach.ENABLE_EXTERNAL_OUTREACH_LLM = False
        try:
            data = await create_outreach_draft(OutreachDraftBody(
                candidateId=body.candidate_id,
                jobId=body.job_id,
                candidateName=body.candidate_name,
                jobTitle=body.job_title,
            ))
        finally:
            outreach.ENABLE_EXTERNAL_OUTREACH_LLM = previous
        return AgentActionResult(type="outreach_draft_created", data=data)

    if action_type == "RESOLVE_REVIEW":
        body = AgentResolveReviewParams(**params)
        data = await resolve_review_task(body.case_id, ResolveBody(resolution=body.resolution, reviewer="human_operator"))
        return AgentActionResult(type="review_resolved", data={"case_id": body.case_id, "resolution": body.resolution, **data})

    if action_type == "BULK_REFRESH_CANDIDATES":
        body = AgentBulkRefreshParams(**params)
        data = await with_heuristic_extraction(
            lambda: maintenance_bulk_refresh_candidates(BulkRefreshBody(ids=body.ids))
        )
        return AgentActionResult(type="candidates_refreshed", data=data)

    if action_type == "PROCESS_INTAKE":
        body = AgentProcessIntakeParams(**params)
        data = await with_heuristic_extraction(lambda: process_intake(body.limit))
        return AgentActionResult(type="intake_processed", data=data)

    raise ValueError(f"Unsupported agent action: {action_type}")


def _agent_help_text(candidates: list, jobs: list, pending_count: int) -> str:
    return (
        "I can prepare Linnify talent-pool workflow actions for human confirmation:\n\n"
        "- Create a job requirement\n"
        "- Run a shortlist for an existing job\n"
        "- Prepare an outreach draft for review\n"
        "- Resolve review items\n"
        "- Find stale profiles or refresh selected candidates\n"
        "- Process provided intake files\n\n"
        f"Current system: **{len(candidates)} candidates**, **{len(jobs)} jobs**, **{pending_count} pending reviews**."
    )


def _extract_job_params(text: str) -> dict:
    params: dict = {"title": "", "department": "Engineering", "location": "Remote", "must_have": [], "nice_to_have": []}
    direct_role_m = re.search(
        r"(?:create|add|open|new|post)\s+(?:a|an)?\s*(.+?)(?:\s+(?:role|position|job)\b|\s+in\b|\s+with\b|,|\.|$)",
        text,
        re.IGNORECASE,
    )
    if direct_role_m:
        params["title"] = direct_role_m.group(1).strip().title()

    title_m = re.search(
        r"(?:for (?:a|an) )([\w\s]+?)(?:\s+(?:role|position|job|engineer|developer|manager|analyst|designer|at|in|with|,|$))",
        text, re.IGNORECASE
    )
    if title_m and not params["title"]:
        params["title"] = title_m.group(1).strip().title()
    elif not params["title"]:
        role_m = re.search(
            r"([\w\s]+?)\s+(?:role|position|engineer|developer|manager|analyst|designer)\b",
            text, re.IGNORECASE
        )
        if role_m:
            params["title"] = role_m.group(0).strip().title()
    params["title"] = re.sub(
        r"^(create|add|open|new|post)\s+(a|an)?\s*",
        "",
        params["title"],
        flags=re.IGNORECASE,
    ).strip()
    params["title"] = re.sub(r"\s+(role|position|job)$", "", params["title"], flags=re.IGNORECASE).strip()

    loc_m = re.search(r"(?:in|at|based in|located in)\s+([\w\s,]+?)(?:\s+with|\s+who|\s+and|,|\.|$)", text, re.IGNORECASE)
    if loc_m:
        params["location"] = loc_m.group(1).strip()

    known_skills = [
        "Python", "JavaScript", "TypeScript", "Java", "React", "Node.js", "AWS", "Go", "Rust",
        "SQL", "Kubernetes", "Docker", "FastAPI", "Django", "Vue", "Angular", "PostgreSQL",
        "MongoDB", "Machine Learning", "LLMs", "NLP", "GCP", "Azure", "C++", "C#",
        "GDScript", "Godot", "Kotlin", "Swift", "Unity", "Unreal", "Flutter", "Dart",
        "Redis", "Elasticsearch", "GraphQL", "Terraform", "Ansible", "Spark", "Kafka",
    ]
    found = [s for s in known_skills if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE)]
    if not found:
        print(f"[chat] Regex skill extraction found no matches for: {text[:80]!r}")
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
        lines.append(f"- **{j.get('title')}** - {j.get('department', '')} / {j.get('location', '')} `{j.get('status', 'MATCHING')}`")
    return "\n".join(lines)


@app.post("/api/gemini/chat")
async def gemini_chat(body: _GeminiChatBody) -> dict:
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    context = body.context
    last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    lower_msg = last_user_msg.lower()

    candidates: list = context.get("candidates", [])
    jobs: list = context.get("jobs", [])
    review_tasks: list = context.get("reviewTasks", [])
    pending_count = sum(1 for t in review_tasks if t.get("status") == "pending")
    actions_taken: list[AgentActionResult] = []
    proposals: list[AgentProposal] = []
    errors: list[str] = []
    candidate_profiles: list[dict] = []
    for record_id in _candidate_record_ids():
        rec = load_record(record_id)
        if rec and not rec.state.archived:
            candidate_profiles.append({
                "id": record_id,
                "name": rec.identity.primary_name or "Unknown",
                "seniority": rec.profile.seniority or "Unknown",
                "location": rec.profile.location or "",
                "skills": rec.profile.technologies_used or [],
                "summary": rec.profile.summary or rec.profile.headline or "",
            })

    create_intent = any(p in lower_msg for p in [
        "create job", "add job", "new job", "post job",
        "create a job", "add a job", "create a new job", "create a role", "add a role",
        "open a role", "new role",
    ]) or (
        re.search(r"\b(create|add|open|post|new)\b", lower_msg)
        and re.search(r"\b(role|position|job|engineer|developer|manager|analyst|designer)\b", lower_msg)
    )
    search_intent = any(p in lower_msg for p in [
        "find job", "search job", "list job", "show job",
        "what jobs", "which jobs", "show me job", "find a job",
    ])
    shortlist_intent = "shortlist" in lower_msg or "rank candidate" in lower_msg or "match candidates" in lower_msg
    outreach_intent = "outreach" in lower_msg or "email draft" in lower_msg or "draft email" in lower_msg
    resolve_intent = any(p in lower_msg for p in ["resolve review", "approve review", "reject review", "purge review", "approve case", "reject case", "purge case"])
    refresh_intent = "refresh" in lower_msg or "bulk update" in lower_msg or "bulk refresh" in lower_msg
    intake_intent = "process intake" in lower_msg or "ingest intake" in lower_msg or "import intake" in lower_msg
    stale_intent = "stale" in lower_msg or "outdated" in lower_msg or "not updated" in lower_msg

    response_text = ""

    if create_intent:
        params = _extract_job_params(last_user_msg)
        if params["title"]:
            job_body = AgentCreateJobParams(
                title=params["title"],
                department=params["department"],
                location=params["location"],
                must_have=params["must_have"],
                nice_to_have=params["nice_to_have"],
            )
            skills_str = ", ".join(params["must_have"]) if params["must_have"] else "to be defined"
            proposals.append(_agent_proposal(
                "CREATE_JOB",
                f"Create job: {params['title']}",
                f"Create a {params['department']} job requirement in {params['location']} with required skills: {skills_str}.",
                job_body,
                "Adds one job requirement. No candidates are shortlisted until you run matching.",
            ))
            response_text = "I prepared a job requirement proposal. Confirm it to add the job to Jobs & Shortlist."
        else:
            response_text = (
                "Please include the role title before I prepare the job proposal, for example:\n\n"
                "_Create a Senior Python Developer role in London with FastAPI and Docker._"
            )
    elif shortlist_intent:
        job = _find_job_from_text(last_user_msg, jobs)
        if job:
            body = AgentShortlistParams(req_id=job.get("id", ""), top_n=5)
            proposals.append(_agent_proposal(
                "RUN_SHORTLIST",
                f"Run shortlist: {job.get('title', 'job')}",
                f"Rank active talent-pool candidates for {_job_label(job)}.",
                body,
                "Updates the selected job with a ranked shortlist and evidence rows.",
            ))
            response_text = "I prepared a shortlist run. Confirm it to score and rank candidates for this job."
        else:
            response_text = "I need a specific job before preparing a shortlist run. Try naming the job title or use its `req_...` id."
    elif outreach_intent:
        job = _find_job_from_text(last_user_msg, jobs)
        candidate = _find_candidate_from_text(last_user_msg, candidates, jobs, job)
        if job and candidate:
            body = AgentOutreachDraftParams(
                candidate_id=candidate.get("id", ""),
                job_id=job.get("id", ""),
                candidate_name=candidate.get("name", ""),
                job_title=job.get("title", ""),
            )
            proposals.append(_agent_proposal(
                "CREATE_OUTREACH_DRAFT",
                f"Draft outreach: {candidate.get('name', 'candidate')}",
                f"Prepare a human-reviewed outreach draft for {candidate.get('name', 'the selected candidate')} about {job.get('title', 'the selected job')}.",
                body,
                "Creates an outreach draft in Outreach & Review. It does not send email or contact the candidate.",
            ))
            response_text = "I prepared an outreach-draft proposal. Confirm it to add the draft to the review queue."
        else:
            response_text = "I need both a candidate and a job before drafting outreach. Name the candidate/job or use their ids."
    elif resolve_intent:
        task = _find_review_task_from_text(last_user_msg, review_tasks)
        if task:
            resolution = _resolution_from_text(last_user_msg)
            body = AgentResolveReviewParams(case_id=task.get("id", ""), resolution=resolution)
            proposals.append(_agent_proposal(
                "RESOLVE_REVIEW",
                f"Resolve review: {task.get('id', '')[:12]}",
                f"Mark review case `{task.get('id', '')}` as {resolution}.",
                body,
                "Changes the review queue. Purge resolutions may archive the candidate record.",
            ))
            response_text = "I prepared a review-resolution proposal. Confirm it only after checking the review item."
        else:
            response_text = "I need the review case id or a unique pending review item before preparing a resolution."
    elif intake_intent:
        limit_m = re.search(r"\b(\d{1,3})\b", last_user_msg)
        limit = int(limit_m.group(1)) if limit_m else 25
        body = AgentProcessIntakeParams(limit=limit)
        proposals.append(_agent_proposal(
            "PROCESS_INTAKE",
            f"Process intake files ({body.limit})",
            f"Import up to {body.limit} provided `.pdf` or `.txt` files from the intake folder.",
            body,
            "Creates or updates candidate records from files already placed in the local intake folder.",
        ))
        response_text = "I prepared an intake-processing proposal. Confirm it to import local intake files."
    elif refresh_intent:
        ids = _candidate_ids_from_text(last_user_msg, candidates)
        if stale_intent and not ids:
            months_m = re.search(r"(\d{1,2})\s*month", lower_msg)
            months = int(months_m.group(1)) if months_m else 6
            stale_result = await list_stale_candidates(months)
            ids = [c.get("id", "") for c in stale_result.get("candidates", []) if c.get("id")]
        if ids:
            body = AgentBulkRefreshParams(ids=ids)
            proposals.append(_agent_proposal(
                "BULK_REFRESH_CANDIDATES",
                f"Refresh {len(ids)} candidate profile{'s' if len(ids) != 1 else ''}",
                "Update selected candidate records from already stored/profile-provided data.",
                body,
                "Updates candidate records locally and may add review cases for low-confidence changes. No external LinkedIn scraping is performed.",
            ))
            response_text = "I prepared a candidate-refresh proposal. Confirm it to update the selected records locally."
        else:
            response_text = "I need candidate ids, candidate names, or a stale-profile request before preparing a refresh."
    elif stale_intent:
        months_m = re.search(r"(\d{1,2})\s*month", lower_msg)
        months = int(months_m.group(1)) if months_m else 6
        result = await list_stale_candidates(months)
        stale = result.get("candidates", [])
        actions_taken.append(AgentActionResult(type="stale_candidates_listed", data=result))
        if stale:
            lines = [f"Found **{len(stale)} stale candidate(s)** older than {result.get('months', months)} months:\n"]
            for candidate in stale[:8]:
                lines.append(f"- **{candidate.get('name')}** `{candidate.get('id')}`")
            response_text = "\n".join(lines)
        else:
            response_text = f"No stale candidates found for the {result.get('months', months)} month threshold."
    elif search_intent:
        response_text = _format_jobs_list(jobs, last_user_msg)
    elif any(p in lower_msg for p in ["which candidates", "who knows", "know ", "skills", "experience with", "worked with"]):
        stopwords = {
            "which", "candidates", "candidate", "who", "knows", "know", "skills", "skill",
            "experience", "with", "worked", "show", "have", "has", "the", "and", "for",
        }
        terms = [tok for tok in re.findall(r"[a-z0-9+#.]+", lower_msg) if len(tok) > 2 and tok not in stopwords]
        matches = []
        for profile in candidate_profiles:
            haystack = " ".join([
                profile.get("seniority", ""),
                profile.get("location", ""),
                " ".join(profile.get("skills", [])),
                profile.get("summary", ""),
            ]).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                matches.append((score, profile))
        matches.sort(key=lambda row: row[0], reverse=True)
        if matches:
            lines = [f"Found **{len(matches)} candidate(s)** matching {', '.join(terms) or 'your query'}:\n"]
            for _, profile in matches[:8]:
                skills = ", ".join(profile.get("skills", [])[:5]) or "No skills listed"
                lines.append(f"- **{profile.get('name')}** `{profile.get('id')}` - {profile.get('seniority')} / {skills}")
            response_text = "\n".join(lines)
        else:
            response_text = "I did not find a local candidate match for that skill query."
    elif any(p in lower_msg for p in ["candidate", "talent", "pool", "how many"]):
        response_text = (
            f"**Talent Pool Overview**\n\n"
            f"- Total candidates: **{len(candidates)}**\n"
            f"- Active jobs: **{len(jobs)}**\n"
            f"- Pending compliance reviews: **{pending_count}**\n\n"
            "Use the Talent Pool screen for detailed filtering."
        )
    elif any(p in lower_msg for p in ["compliance", "gdpr", "pending", "review"]):
        pending_tasks = [t for t in review_tasks if t.get("status") == "pending"]
        if pending_tasks:
            lines = [f"**{len(pending_tasks)} pending review task(s):**\n"]
            for t in pending_tasks[:5]:
                lines.append(f"- `{t.get('id','')}` - {t.get('type','UNKNOWN').replace('_',' ')}")
            response_text = "\n".join(lines)
        else:
            response_text = "No pending review tasks. The candidate pool is clear right now."
    else:
        response_text = _agent_help_text(candidates, jobs, pending_count)

    response = AgentChatResponse(text=response_text, actions=actions_taken, proposals=proposals, errors=errors)
    return _dump_model(response)


@app.post("/api/agent/actions/{proposal_id}/confirm")
async def confirm_agent_action(proposal_id: str):
    try:
        proposal = _consume_agent_proposal(proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Agent proposal '{proposal_id}' not found or already handled")

    try:
        result = await _execute_agent_proposal(proposal)
    except HTTPException as exc:
        _agent_event("agent_action_failed", proposal=proposal, actor="human", error=str(exc.detail))
        raise
    except Exception as exc:
        _agent_event("agent_action_failed", proposal=proposal, actor="human", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))

    data = _dump_model(result) if isinstance(result, BaseModel) else result
    _agent_event("agent_action_confirmed", proposal=proposal, actor="human", result=data)
    response = AgentChatResponse(
        text=f"Confirmed: {proposal.get('label', proposal.get('type', 'agent action'))}.",
        actions=[result],
        proposals=[],
        errors=[],
    )
    return _dump_model(response)


# ---------------------------------------------------------------------------
# Spreadsheet ingest routes
# ---------------------------------------------------------------------------

from web.app_csv_patch import apply_csv_routes
apply_csv_routes(app)


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
            raise HTTPException(status_code=404, detail="UI not built yet - run: cd ui && npm run build")
        return FileResponse(str(index))


def start_server():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8080, reload=True)


if __name__ == "__main__":
    start_server()
