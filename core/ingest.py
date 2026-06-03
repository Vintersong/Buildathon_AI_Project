import os
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from filelock import FileLock

from .config import (
    RECORDS_DIR,
    INTAKE_DIR,
    QUARANTINE_DIR,
    INGEST_MANIFEST_PATH,
    LOGS_DIR,
    REQUIREMENTS_DIR,
    get_confidence_threshold,
)
from .schemas import CandidateRecord, State, Compliance, Scores
from .store import save_record, load_record, record_exists
from .extract import extract_candidate_data
from .dedup import find_existing_by_identity as find_duplicate
from .compliance import check_and_generate_review_cases

MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "10"))
_OCR_MIN_CHARS_PER_PAGE = 50

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
    import io
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


def log_error(event: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "error_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _ocr_page(page) -> str:
    if not _OCR_AVAILABLE:
        return ""
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    return pytesseract.image_to_string(img)


def _read_file(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        if fitz is None:
            raise ValueError("PDF parsing unavailable: PyMuPDF is not installed")
        full_text = ""
        ocr_used = False
        try:
            with fitz.open(file_path) as doc:
                if doc.page_count > MAX_PDF_PAGES:
                    raise ValueError(
                        f"PDF has {doc.page_count} pages which exceeds the "
                        f"maximum of {MAX_PDF_PAGES}. Adjust MAX_PDF_PAGES env var to raise the limit."
                    )
                for page in doc:
                    page_text = page.get_text()
                    if len(page_text.strip()) < _OCR_MIN_CHARS_PER_PAGE:
                        if _OCR_AVAILABLE:
                            page_text = _ocr_page(page)
                            ocr_used = True
                    full_text += page_text
            if ocr_used:
                print(f"[ingest] OCR fallback used for {file_path.name}")
            return full_text
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"PDF parsing failed: {str(e)}")
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def _merge_record(record: CandidateRecord, extraction, now: str) -> list[dict]:
    """
    Merge a new extraction into an existing record.

    Strategy:
    - OVERWRITE: point-in-time fields where the newest CV is ground truth
    - UNION (order-preserving dedup): accumulative fields where history must be preserved

    Returns a list of change dicts for the provenance audit event.
    """
    changes = []

    overwrite_map = [
        ("profile", "seniority",           extraction.seniority),
        ("profile", "years_of_experience",  extraction.years_of_experience),
        ("profile", "location",             extraction.location),
        ("profile", "summary",              extraction.summary),
        ("profile", "headline",             extraction.headline if hasattr(extraction, "headline") else None),
        ("identity", "primary_name",        extraction.name),
        ("identity", "linkedin_url",        extraction.linkedin_url),
    ]
    for section, field, new_val in overwrite_map:
        if new_val is None:
            continue
        obj = getattr(record, section)
        old_val = getattr(obj, field, None)
        if old_val != new_val:
            setattr(obj, field, new_val)
            changes.append({
                "operation": "replace",
                "path": f"/{section}/{field}",
                "old_value": old_val,
                "new_value": new_val,
            })

    def _union(existing: list, incoming: list, path: str) -> list:
        existing = existing or []
        incoming = incoming or []
        merged = list(dict.fromkeys(existing + incoming))
        if merged != existing:
            changes.append({"operation": "union", "path": path, "added": [x for x in incoming if x not in existing]})
        return merged

    record.profile.technologies_used = _union(
        record.profile.technologies_used, extraction.technologies_used or [], "/profile/technologies_used"
    )
    record.profile.previous_jobs = _union(
        record.profile.previous_jobs, extraction.previous_jobs or [], "/profile/previous_jobs"
    )
    record.profile.study_degrees = _union(
        record.profile.study_degrees, extraction.study_degrees or [], "/profile/study_degrees"
    )
    record.profile.languages_spoken = _union(
        record.profile.languages_spoken, extraction.languages_spoken or [], "/profile/languages_spoken"
    )
    record.profile.projects_developed = _union(
        record.profile.projects_developed, extraction.projects_developed or [], "/profile/projects_developed"
    )

    new_emails = [e for e in (extraction.emails or []) if e not in record.identity.emails]
    if new_emails:
        record.identity.emails.extend(new_emails)
        changes.append({"operation": "union", "path": "/identity/emails", "added": new_emails})

    record.scores.extraction_confidence = extraction.extraction_confidence
    record.compliance.sensitive_data_detected = getattr(extraction, "sensitive_data_detected", None) or []
    record.updated_at = now

    return changes


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if not INGEST_MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(INGEST_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _update_manifest(file_hash: str, record_id: str, filename: str) -> None:
    manifest = _load_manifest()
    manifest[file_hash] = {
        "record_id": record_id,
        "filename": filename,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = INGEST_MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(INGEST_MANIFEST_PATH)


def ingest_file(
    file_path: Path,
    *,
    force: bool = False,
    target_record_id: Optional[str] = None,
) -> dict:
    """
    Ingest a single CV file (PDF or TXT).

    Returns a result dict with keys: record_id, status ('created'|'updated'|'skipped'), changes.
    """
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    file_hash = _file_hash(file_path)
    manifest = _load_manifest()

    if not force and file_hash in manifest:
        existing_id = manifest[file_hash]["record_id"]
        return {"record_id": existing_id, "status": "skipped", "changes": []}

    try:
        raw_text = _read_file(file_path)
    except ValueError as e:
        log_error({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "ingest_file_read_error",
            "file": str(file_path),
            "error": str(e),
        })
        raise

    extraction, model_info = extract_candidate_data(raw_text)

    now = datetime.now(timezone.utc).isoformat()

    if target_record_id and record_exists(target_record_id):
        record_id = target_record_id
        record = load_record(record_id)
        changes = _merge_record(record, extraction, now)
        event = {
            "timestamp": now,
            "event": "cv_reimport",
            "file": file_path.name,
            "file_hash": file_hash,
            "model": model_info,
            "changes": changes,
        }
        save_record(record_id, record, event=event)
        _update_manifest(file_hash, record_id, file_path.name)
        return {"record_id": record_id, "status": "updated", "changes": changes}

    dup_id = find_duplicate(extraction)
    if dup_id:
        record = load_record(dup_id)
        changes = _merge_record(record, extraction, now)
        event = {
            "timestamp": now,
            "event": "cv_reimport_dedup",
            "file": file_path.name,
            "file_hash": file_hash,
            "model": model_info,
            "changes": changes,
        }
        save_record(dup_id, record, event=event)
        _update_manifest(file_hash, dup_id, file_path.name)
        return {"record_id": dup_id, "status": "updated", "changes": changes}

    from datetime import timedelta
    record_id = f"cand_{uuid.uuid4().hex[:12]}"
    retention_until = (datetime.now(timezone.utc) + timedelta(days=730)).isoformat()

    from .schemas import Identity, Profile, Scores, Compliance, State

    record = CandidateRecord(
        created_at=now,
        updated_at=now,
        identity=Identity(
            primary_name=extraction.name,
            linkedin_url=extraction.linkedin_url,
            emails=extraction.emails or [],
        ),
        profile=Profile(
            headline=extraction.headline if hasattr(extraction, "headline") else None,
            summary=extraction.summary,
            seniority=extraction.seniority,
            years_of_experience=extraction.years_of_experience,
            technologies_used=extraction.technologies_used or [],
            languages_spoken=extraction.languages_spoken or [],
            previous_jobs=extraction.previous_jobs or [],
            study_degrees=extraction.study_degrees or [],
            location=extraction.location,
            projects_developed=extraction.projects_developed or [],
        ),
        scores=Scores(extraction_confidence=extraction.extraction_confidence),
        compliance=Compliance(
            consent_basis="legitimate_interest",
            source="cv_upload",
            data_region="EEA",
            retention_until=retention_until,
            sensitive_data_detected=getattr(extraction, "sensitive_data_detected", None) or [],
            human_review_required=extraction.extraction_confidence < get_confidence_threshold(),
        ),
        state=State(),
    )

    event = {
        "timestamp": now,
        "event": "cv_import",
        "file": file_path.name,
        "file_hash": file_hash,
        "model": model_info,
        "changes": [],
    }
    save_record(record_id, record, event=event)
    _update_manifest(file_hash, record_id, file_path.name)
    check_and_generate_review_cases(record_id, record)
    return {"record_id": record_id, "status": "created", "changes": []}
