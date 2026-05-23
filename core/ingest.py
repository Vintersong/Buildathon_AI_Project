import os
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from filelock import FileLock
import fitz  # PyMuPDF

from .config import MANIFEST_PATH, QUARANTINE_DIR, INTAKE_DIR
from .schemas import CandidateRecord, Identity, Profile, State, Compliance, Scores
from .extract import extract_candidate_data
from .store import load_record, save_record
from .events import log_error

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
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        text = ""
        try:
            with fitz.open(file_path) as doc:
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
        
    # 4. LLM Extraction
    extraction, model_info = extract_candidate_data(raw_text)
    
    # 5. Record Creation / Update Projection
    record_id = existing_record_id or f"cand_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"
    
    record = load_record(record_id)
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
                headline=extraction.seniority,  # map for now
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
            compliance=Compliance(
                # Enforce HITL review if low confidence
                human_review_required=(extraction.extraction_confidence < 0.75)
            )
        )
    else:
        # Update existing - logic for merging fields safely
        record.updated_at = now
        # Simplistic overwrite for the buildathon, in reality we'd append or compare
        record.profile.technologies_used = list(set(record.profile.technologies_used + extraction.technologies_used))
        record.scores.extraction_confidence = extraction.extraction_confidence
    
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
            "reason": "low_extraction_confidence" if record.compliance.human_review_required else None
        }
    }
    
    # 7. Save Atomically
    save_record(record_id, record, event=event)
    
    # 8. Update manifest
    update_manifest(file_hash, record_id)
    
    print(f"Successfully ingested {file_path.name} into {record_id}")
    return record_id

def _quarantine_security(file_path: Path, reason: str):
    quarantine_id = f"sec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    folder = QUARANTINE_DIR / "security_rejections"
    
    data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "attempted_path": str(file_path)
    }
    
    with open(folder / f"{quarantine_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
