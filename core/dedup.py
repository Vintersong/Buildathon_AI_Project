"""Identity-based deduplication: find an existing record matching a new extraction."""
import hashlib
from typing import Optional

from .schemas import CandidateExtraction
from .store import load_record
from .config import RECORD_INDEX_PATH
import json

# Minimum character length for a name to be considered non-trivial for matching.
# Raised from 3 to 6 to avoid false merges on common short names (e.g. "Anna", "Ivan").
_MIN_NAME_LEN = 6


def _load_index() -> dict:
    try:
        with open(RECORD_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def find_existing_by_identity(extraction: CandidateExtraction) -> Optional[str]:
    """
    Search the record index for a candidate that matches the extraction by:
      1. Email hash overlap — checked against index directly (O(1) per record)
         when email_hashes are present in the index; falls back to full record
         load for legacy index entries that predate this field.
      2. Exact name match (fallback, only for names longer than _MIN_NAME_LEN chars).

    Returns the record_id of the first match, or None if no duplicate found.
    """
    index = _load_index()
    new_email_hashes = {_email_hash(e) for e in (extraction.emails or [])}
    new_name = (extraction.name or "").strip().lower()

    for record_id, meta in index.items():
        # --- Fast path: use pre-computed email hashes from the index ---
        if new_email_hashes and "email_hashes" in meta:
            existing_hashes = set(meta["email_hashes"])
            if new_email_hashes & existing_hashes:
                return record_id
            # Email hashes present but no overlap — skip name check too,
            # because a different email set means a different identity.
            continue

        # --- Slow path: index entry predates email_hashes; load full record ---
        rec = load_record(record_id)
        if not rec:
            continue

        if new_email_hashes:
            existing_hashes = {_email_hash(e) for e in rec.identity.emails}
            if new_email_hashes & existing_hashes:
                return record_id

        # Name match only when no emails are available on the new extraction
        if not extraction.emails and new_name and len(new_name) >= _MIN_NAME_LEN:
            existing_name = (rec.identity.primary_name or "").strip().lower()
            if new_name == existing_name:
                return record_id

    return None
