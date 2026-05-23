import os
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from filelock import FileLock
import fitz  # PyMuPDF

from .config import (
    MANIFEST_PATH,
    QUARANTINE_DIR,
    INTAKE_DIR,
    MAX_INGEST_FILE_BYTES,
    MAX_PDF_PAGES,
)
from .schemas import CandidateRecord, Identity, Profile, State, Compliance, Scores
from .extract import extract_candidate_data
from .store import load_record, save_record
from .events import log_error
from .dedup import find_existing_by_identity

# Default consent basis applied to newly ingested records.
# Override via DEFAULT_CONSENT_BASIS env var or by patching in tests.
DEFAULT_CONSENT_BASIS: Optional[str] = os.getenv("DEFAULT_CONSENT_BASIS")

# OCR support — optional, gracefully degraded if tesseract is not installed
try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

_OCR_MIN_CHARS_PER_PAGE = 50  # pages with fewer chars are treated as image-based


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


def _ocr_page(page) -> str:
    """Render a PDF page to an image and run Tesseract OCR on it."""
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from supported file types, with OCR fallback for image-based PDFs."""
    size = file_path.stat().st_size
    if size > MAX_INGEST_FILE_BYTES:
        raise ValueError(
            f"File exceeds maximum allowed size of {MAX_INGEST_FILE_BYTES} bytes "
            f"(got {size} bytes). Adjust MAX_INGEST_FILE_BYTES env var to raise the limit."
        )

    ext = file_path.suffix.lower()
    if ext == ".pdf":
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
                        # Image-based page — fall back to OCR if available
                        if _OCR_AVAILABLE:
                            page_text = _ocr_page(page)
                            ocr_used = True
                        # else: keep whatever sparse text was extracted
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


def ingest_file(file_path: Path, source_type: str = "document", force: bool = False) -> str:
    """
    Ingest a file: hash, dedup (hash + identity), extract text, run LLM extract,
    create or update record, then run compliance checks.
    Returns the record_id.
    """
    # 1. Path allowlist check
    if not file_path.resolve().is_relative_to(INTAKE_DIR.resolve()):
        _quarantine_security(file_path, "path_not_allowed")
        raise PermissionError("File path is outside configured intake roots")

    # 2. Hash-based duplicate check
    file_hash = compute_sha256(file_path)
    existing_by_hash = check_manifest(file_hash)

    if existing_by_hash and not force:
        print(f"Skipping {file_path.name}: already ingested (hash match) into {existing_by_hash}")
        return existing_by_hash

    # 3. Extract Text (size + page limits enforced inside)
    try:
        raw_text = extract_text_from_file(file_path)
    except Exception as e:
        log_error({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stage": "text_extraction",
            "source_file": file_path.name,
            "source_hash": file_hash,
            "error_type": "ParseFailed",
            "message": str(e),
        })
        raise

    # 4. LLM Extraction
    extraction, model_info = extract_candidate_data(raw_text)

    # 5. Identity-based duplicate check (catches same candidate, different file)
    existing_by_identity = find_existing_by_identity(extraction)
    existing_record_id = existing_by_hash or existing_by_identity

    if existing_by_identity and not existing_by_hash:
        print(f"Identity match found for {file_path.name}: merging into existing record {existing_by_identity}")

    # 6. Record Creation / Update
    record_id = existing_record_id or f"cand_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"

    record = load_record(record_id)
    if not record:
        record = CandidateRecord(
            created_at=now,
            updated_at=now,
            identity=Identity(
                primary_name=extraction.name,
                emails=extraction.emails,
                phones=extraction.phones,
                linkedin_url=extraction.linkedin_url,
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
                projects_developed=extraction.projects_developed,
            ),
            scores=Scores(
                extraction_confidence=extraction.extraction_confidence,
            ),
            compliance=Compliance(
                consent_basis=DEFAULT_CONSENT_BASIS,
                human_review_required=(extraction.extraction_confidence < 0.75),
            ),
        )
    else:
        # Merge into existing record
        record.updated_at = now
        record.profile.technologies_used = list(
            set(record.profile.technologies_used) | set(extraction.technologies_used)
        )
        existing_jobs = set(record.profile.previous_jobs)
        for job in extraction.previous_jobs:
            if job not in existing_jobs:
                record.profile.previous_jobs.append(job)
                existing_jobs.add(job)
        if extraction.summary:
            record.profile.summary = extraction.summary
        record.scores.extraction_confidence = extraction.extraction_confidence

    # 7. Provenance Event
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "source_ingested",
        "timestamp": now,
        "source": {
            "file_name": file_path.name,
            "source_type": source_type,
            "sha256": file_hash,
        },
        "actor": {
            "type": "system",
            "tool": "record_ingest",
        },
        "model": model_info,
        "changes": [{"operation": "replace", "path": "/", "value": "full_extraction"}],
        "review": {
            "required": record.compliance.human_review_required,
            "reason": "low_extraction_confidence" if record.compliance.human_review_required else None,
        },
    }

    # 8. Save Atomically
    save_record(record_id, record, event=event)

    # 9. Run compliance checks and queue any violations for human review
    try:
        from .compliance import evaluate_compliance
        from .review import add_to_queue
        cases = evaluate_compliance(record_id)
        if cases:
            add_to_queue(cases)
    except Exception as e:
        log_error({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stage": "post_ingest_compliance",
            "record_id": record_id,
            "error_type": "ComplianceCheckFailed",
            "message": str(e),
        })

    # 10. Update manifest
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
        "attempted_path": str(file_path),
    }

    with open(folder / f"{quarantine_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
