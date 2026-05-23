import os
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from filelock import FileLock
import fitz  # PyMuPDF

from .config import (
    MANIFEST_PATH,
    QUARANTINE_DIR,
    INTAKE_DIR,
    MAX_INGEST_FILE_BYTES,
    MAX_PDF_PAGES,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_DATA_REGION,
    DEFAULT_CONSENT_BASIS,
)
from .schemas import CandidateRecord, Identity, Profile, State, Compliance, Scores
from .extract import extract_candidate_data
from .store import load_record, save_record
from .events import log_error
from .compliance import evaluate_compliance
from .review import add_to_queue
from .security import redact_pii

def compute_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return f"sha256:{sha256_hash.hexdigest()}"

def check_manifest(file_hash: str) -> Optional[str]:
    """Check if hash was already ingested. Returns record_id if it was."""
    lock = FileLock(f"{MANIFEST_PATH}.lock")
    with lock:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            return manifest.get(file_hash)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

def update_manifest(file_hash: str, record_id: str):
    lock = FileLock(f"{MANIFEST_PATH}.lock")
    with lock:
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            manifest = {}
        
        manifest[file_hash] = record_id
        
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

def extract_text_from_file(file_path: Path) -> str:
    """Extract text from supported file types."""
    size = file_path.stat().st_size
    if size > MAX_INGEST_FILE_BYTES:
        raise ValueError(f"File exceeds maximum allowed size of {MAX_INGEST_FILE_BYTES} bytes")

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        text = ""
        try:
            with fitz.open(file_path) as doc:
                if doc.page_count > MAX_PDF_PAGES:
                    raise ValueError(f"PDF exceeds maximum allowed page count of {MAX_PDF_PAGES}")
                for page in doc:
                    text += page.get_text()
            return text
        except Exception as e:
            raise ValueError(f"PDF parsing failed: {str(e)}")
    # Extend with docx etc. here if needed
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def ingest_file(file_path: Path, source_type: str = "document", force: bool = False) -> str:
    """
    Ingest a file: hash, check dup, extract text, run LLM extract, create/update record.
    Returns the record_id.
    """
    # 1. Path allowlist check
    if not file_path.resolve().is_relative_to(INTAKE_DIR.resolve()):
        _quarantine_security(file_path, "path_not_allowed")
        raise PermissionError("File path is outside configured intake roots")
    
    # 2. Hash and check manifest
    file_hash = compute_sha256(file_path)
    existing_record_id = check_manifest(file_hash)
    
    if existing_record_id and not force:
        print(f"Skipping {file_path.name}: already ingested into {existing_record_id}")
        return existing_record_id
        
    # 3. Extract Text
    try:
        raw_text = extract_text_from_file(file_path)
    except Exception as e:
        log_error({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stage": "text_extraction",
            "source_file": file_path.name,
            "source_hash": file_hash,
            "error_type": "ParseFailed",
            "message": str(e)
        })
        raise
        
    # 4. Extraction
    extraction, model_info = extract_candidate_data(raw_text)
    
    # 5. Record Creation / Update Projection
    record_id = existing_record_id or f"cand_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"
    
    record = load_record(record_id)
    review_required = _requires_review(extraction, model_info)
    retention_until = (datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)).isoformat() + "Z"

    if not record:
        # Create new
        record = CandidateRecord(
            created_at=now,
            updated_at=now,
            identity=Identity(
                primary_name=extraction.name,
                emails=extraction.emails,
                phones=extraction.phones,
                linkedin_url=extraction.linkedin_url
            ),
            profile=Profile(
                headline=None,
                summary=extraction.summary,
                seniority=extraction.seniority,
                years_of_experience=extraction.years_of_experience,
                study_degrees=extraction.study_degrees,
                technologies_used=extraction.technologies_used,
                languages_spoken=extraction.languages_spoken,
                location=extraction.location,
                previous_jobs=extraction.previous_jobs,
                projects_developed=extraction.projects_developed
            ),
            scores=Scores(
                extraction_confidence=extraction.extraction_confidence
            ),
            state=State(
                status="pending_review" if review_required or not DEFAULT_CONSENT_BASIS else "new",
                last_refreshed_at=now,
            ),
            compliance=Compliance(
                consent_basis=DEFAULT_CONSENT_BASIS,
                source=source_type,
                retention_until=retention_until,
                data_region=DEFAULT_DATA_REGION,
                human_review_required=(review_required or not DEFAULT_CONSENT_BASIS)
            )
        )
    else:
        # Update existing - logic for merging fields safely
        record.updated_at = now
        record.state.last_refreshed_at = now
        _append_unique(record.profile.technologies_used, extraction.technologies_used)
        _append_unique(record.profile.previous_jobs, extraction.previous_jobs)
        _append_unique(record.profile.projects_developed, extraction.projects_developed)
        _append_unique(record.profile.languages_spoken, extraction.languages_spoken)
        _append_unique(record.profile.study_degrees, extraction.study_degrees)
        if extraction.summary:
            record.profile.summary = extraction.summary
        if extraction.seniority:
            record.profile.seniority = extraction.seniority
        if extraction.years_of_experience is not None:
            record.profile.years_of_experience = extraction.years_of_experience
        if extraction.location:
            record.profile.location = extraction.location
        record.scores.extraction_confidence = extraction.extraction_confidence
        if not record.compliance.source:
            record.compliance.source = source_type
        if not record.compliance.retention_until:
            record.compliance.retention_until = retention_until
        if not record.compliance.data_region:
            record.compliance.data_region = DEFAULT_DATA_REGION
        if not record.compliance.consent_basis and DEFAULT_CONSENT_BASIS:
            record.compliance.consent_basis = DEFAULT_CONSENT_BASIS
        if review_required or not record.compliance.consent_basis:
            record.compliance.human_review_required = True
            record.state.status = "pending_review"
    
    # 6. Provenance Event
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "source_ingested",
        "timestamp": now,
        "source": {
            "file_name": file_path.name,
            "source_type": source_type,
            "sha256": file_hash
        },
        "actor": {
            "type": "system",
            "tool": "record_ingest"
        },
        "model": model_info,
        "changes": [{"operation": "replace", "path": "/", "value": "full_extraction"}],
        "review": {
            "required": record.compliance.human_review_required,
            "reason": ",".join(extraction.review_flags) if record.compliance.human_review_required else None
        }
    }
    
    # 7. Save Atomically
    save_record(record_id, record, event=event)

    review_cases = evaluate_compliance(record_id)
    if review_cases:
        add_to_queue(review_cases)
    
    # 8. Update manifest
    update_manifest(file_hash, record_id)
    
    print(f"Successfully ingested {file_path.name} into {record_id}")
    return record_id

def _quarantine_security(file_path: Path, reason: str):
    quarantine_id = f"sec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    folder = QUARANTINE_DIR / "security_rejections"
    folder.mkdir(parents=True, exist_ok=True)
    
    data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "attempted_path": redact_pii(str(file_path))
    }
    
    with open(folder / f"{quarantine_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _requires_review(extraction, model_info: Dict[str, Any]) -> bool:
    return (
        extraction.extraction_confidence < 0.75
        or bool(extraction.review_flags)
        or bool(model_info.get("external"))
    )

def _append_unique(target: list, incoming: list):
    for item in incoming or []:
        if item not in target:
            target.append(item)
