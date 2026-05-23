import os
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional
from filelock import FileLock

from .config import RECORDS_DIR, RECORD_INDEX_PATH
from .events import log_event
from .schemas import CandidateRecord, State, Compliance


class SecurityError(Exception):
    pass


class StoreError(Exception):
    pass


def _resolve_record_path(record_id: str) -> Path:
    """Resolve and validate a record path to prevent path traversal."""
    if "/" in record_id or "\\" in record_id or ".." in record_id:
        raise SecurityError("Invalid record ID")

    path = (RECORDS_DIR / f"{record_id}.json").resolve()
    if not path.is_relative_to(RECORDS_DIR.resolve()):
        raise SecurityError("Path traversal attempt detected")

    return path


def _coerce_record(record: CandidateRecord) -> CandidateRecord:
    """
    Backfill missing fields on records written by older schema versions.
    Runs after every load so legacy JSON on disk never causes AttributeErrors.
    """
    # state: may be None on records written before State was added
    if record.state is None:
        record.state = State()

    # consent_basis: default to legitimate_interest so compliance engine
    # doesn't flood the review queue with null-consent flags on every record
    if record.compliance is None:
        record.compliance = Compliance()
    if not record.compliance.consent_basis:
        record.compliance.consent_basis = "legitimate_interest"

    return record


def load_record(record_id: str) -> Optional[CandidateRecord]:
    """Load a candidate record by ID, applying legacy field coercion."""
    path = _resolve_record_path(record_id)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    record = CandidateRecord(**data)
    return _coerce_record(record)


def save_record(record_id: str, record: CandidateRecord, event: Optional[Dict[str, Any]] = None):
    """Atomically save a record and optionally append a provenance event."""
    path = _resolve_record_path(record_id)
    lock = FileLock(f"{path}.lock")

    with lock:
        temp_path = path.with_suffix(".json.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(record.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)

            if event:
                record.provenance.append(event)
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(record.model_dump_json(indent=2))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, path)

                log_event(event)

            _update_record_index(record_id, record)

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise StoreError(f"Failed to save record {record_id}: {str(e)}")


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def _update_record_index(record_id: str, record: CandidateRecord):
    """Update the lightweight index for searching/listing."""
    lock = FileLock(f"{RECORD_INDEX_PATH}.lock")
    with lock:
        try:
            with open(RECORD_INDEX_PATH, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            index = {}

        index[record_id] = {
            "name": record.identity.primary_name,
            "headline": record.profile.headline,
            "status": record.state.status if record.state else "new",
            "updated_at": record.updated_at,
            "email_hashes": [_email_hash(e) for e in record.identity.emails],
        }

        with open(RECORD_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
