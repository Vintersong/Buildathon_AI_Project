"""Identity-based deduplication: find an existing record matching a new extraction."""
from typing import Optional

from .schemas import CandidateExtraction
from .store import load_record
from .config import RECORD_INDEX_PATH
import json


def _load_index() -> dict:
    try:
        with open(RECORD_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def find_existing_by_identity(extraction: CandidateExtraction) -> Optional[str]:
    """
    Search the record index for a candidate that matches the extraction by:
      1. Email overlap (strongest signal)
      2. Exact name match (fallback)

    Returns the record_id of the first match, or None if no duplicate found.
    """
    index = _load_index()
    new_emails = {e.lower().strip() for e in (extraction.emails or [])}
    new_name = (extraction.name or "").strip().lower()

    for record_id in index:
        rec = load_record(record_id)
        if not rec:
            continue

        # 1. Email match
        if new_emails:
            existing_emails = {e.lower().strip() for e in rec.identity.emails}
            if new_emails & existing_emails:
                return record_id

        # 2. Name match (only if name is non-trivial)
        if new_name and len(new_name) > 3:
            existing_name = (rec.identity.primary_name or "").strip().lower()
            if new_name == existing_name:
                return record_id

    return None
