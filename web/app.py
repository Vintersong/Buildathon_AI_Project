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
    RECORDS_DIR,
    REQUIREMENTS_DIR,
    RECORD_INDEX_PATH,
    INTAKE_DIR,
    PROVIDERS,
    get_active_model,
    get_active_provider,
    get_use_local_llm,
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
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-2.5-flash")
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    sovereign_cloud: bool = Field(default=False)
    use_local_llm: bool = Field(default=False)


class AppConfigResponse(AppConfig):
    """Read shape - exposes which provider keys are set and their last-4 only."""
    gemini_api_key_set: bool = False
    gemini_api_key_last4: Optional[str] = None
    openai_api_key_set: bool = False
    openai_api_key_last4: Optional[str] = None
    anthropic_api_key_set: bool = False
    anthropic_api_key_last4: Optional[str] = None


class AppConfigUpdate(AppConfig):
    """Write shape - optional plaintext keys per provider.

    For each key field: None → leave as-is, "" → clear, other → save.
    """
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None


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
    key_fields = {"gemini_api_key", "openai_api_key", "anthropic_api_key"}
    cfg = AppConfig(**body.model_dump(exclude=key_fields))
    if cfg.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: '{cfg.provider}'")
    try:
        save_app_config(cfg)
        for provider, value in (
            ("gemini", body.gemini_api_key),
            ("openai", body.openai_api_key),
            ("anthropic", body.anthropic_api_key),
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

    from core import llm
    llm_ok = llm.llm_available()

    full_records: list[dict] = []
    for record_id in _candidate_record_ids():
        rec = load_record(record_id)
        if rec and not rec.state.archived:
            full_records.append(_map_candidate_agent_context(record_id, rec))

    if llm_ok:
        records_block = json.dumps(full_records, default=str, ensure_ascii=False)
        system_prompt = (
            f"You are the Linnify AI Talent Pool Manager assistant.\n\n"
            f"System status: {len(full_records)} candidates, {len(jobs)} jobs, {pending_count} pending compliance reviews.\n"
            f"Active jobs: {', '.join(j.get('title','') for j in jobs[:6]) or 'none'}.\n\n"
            f"PII-minimized candidate records (from records/ folder) \u2014 use these to answer questions about\n"
            f"skills, experience, education, location, previous jobs, projects, languages,\n"
            f"compliance, and scores. Do not infer or reveal contact details:\n"
            f"{records_block}\n\n"
            f"Capabilities:\n"
            f"1. CREATE JOBS \u2014 if user wants to create/add a job, include this marker on its own line before your explanation:\n"
            f'   [ACTION:CREATE_JOB] {{"title":"...","department":"...","location":"...","must_have":["..."],"nice_to_have":["..."]}}\n'
            f"2. SEARCH JOBS \u2014 list matching jobs from the active list above.\n"
            f"3. GENERAL \u2014 answer questions about candidates, compliance, GDPR, outreach using the sanitized records above.\n\n"
            f"Be concise and professional."
        )

        try:
            chat_messages = [{"role": "system", "content": system_prompt}]
            for msg in messages:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})
            response_text = llm.complete(chat_messages, json_mode=False)

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
                    f"Job **{params['title']}** has been created and is ready for shortlisting.\n\n"
                    f"- **Location**: {params['location']}\n"
                    f"- **Department**: {params['department']}\n"
                    f"- **Required skills**: {skills_str}\n\n"
                    "Run shortlist from Jobs & Shortlist to rank candidates."
                )
            else:
                response_text = (
                    "I'd be happy to create a job! Please include the role details, for example:\n\n"
                    "_\"Create a job for a Senior Python Developer in London with FastAPI and Docker\"_\n\n"
                    "Or use the **Create job** button in Jobs & Shortlist."
                )
        elif search_intent:
            response_text = _format_jobs_list(jobs, last_user_msg)
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
                lines = [f"**{len(pending_tasks)} pending compliance task(s):**\n"]
                for t in pending_tasks[:5]:
                    lines.append(f"- `{t.get('id','')[:8]}` - {t.get('type','UNKNOWN').replace('_',' ')}")
                response_text = "\n".join(lines)
            else:
                response_text = "No pending compliance tasks. The candidate pool is fully compliant."
        else:
            response_text = (
                f"I'm the **Linnify Talent Pool assistant**. Here's what I can do:\n\n"
                f"- **Create jobs**: _\"Create a job for a Senior React Developer in Berlin\"_\n"
                f"- **Search jobs**: _\"Find all engineering roles\"_ or _\"Show remote jobs\"_\n"
                f"- **Pool overview**: _\"How many candidates do we have?\"_\n"
                f"- **Compliance**: _\"What GDPR tasks are pending?\"_\n\n"
                f"Current system: **{len(candidates)} candidates**, **{len(jobs)} jobs**, **{pending_count} pending reviews**."
            )

    return {"text": response_text, "actions": actions_taken}


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
