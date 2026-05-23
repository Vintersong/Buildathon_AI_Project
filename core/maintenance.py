from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from .store import load_record, save_record
from .extract import extract_candidate_data
from .events import log_error
from .config import RECORDS_DIR, STALE_REFRESH_MONTHS


def bulk_refresh(updates: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Process a batch of candidate updates (simulating LinkedIn data pulls).
    `updates` is a list of dicts with 'record_id' and 'raw_text'.
    """
    results = {"success": 0, "failed": 0, "errors": []}

    for update in updates:
        record_id = update.get("record_id")
        raw_text = update.get("raw_text")

        if not record_id or not raw_text:
            results["failed"] += 1
            results["errors"].append({"record_id": record_id, "error": "Missing record_id or raw_text"})
            continue

        record = load_record(record_id)
        if not record:
            results["failed"] += 1
            results["errors"].append({"record_id": record_id, "error": "Record not found"})
            continue

        try:
            extraction, model_info = extract_candidate_data(raw_text)

            now = datetime.utcnow().isoformat() + "Z"
            record.updated_at = now
            record.state.last_refreshed_at = now

            if extraction.technologies_used:
                record.profile.technologies_used = list(
                    set(record.profile.technologies_used) | set(extraction.technologies_used)
                )

            if extraction.previous_jobs:
                # Deduplicate without set() to avoid unhashable-type errors on future schema changes
                existing_jobs = set(record.profile.previous_jobs)
                for job in extraction.previous_jobs:
                    if job not in existing_jobs:
                        record.profile.previous_jobs.append(job)
                        existing_jobs.add(job)

            if extraction.summary:
                record.profile.summary = extraction.summary

            record.scores.extraction_confidence = extraction.extraction_confidence

            event = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "event_type": "bulk_refresh_update",
                "timestamp": now,
                "source": {"source_type": "linkedin_batch_export"},
                "actor": {"type": "system", "tool": "maintenance_bulk_refresh"},
                "model": model_info,
                "changes": [{"operation": "merge", "path": "/profile", "value": "updated_from_linkedin"}],
                "review": {"required": False}
            }

            save_record(record_id, record, event=event)
            results["success"] += 1

        except Exception as e:
            results["failed"] += 1
            error_msg = str(e)
            results["errors"].append({"record_id": record_id, "error": error_msg})
            log_error({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "stage": "bulk_refresh",
                "record_id": record_id,
                "error_type": "RefreshFailed",
                "message": error_msg
            })

    return results


def find_stale_candidates(months: int = STALE_REFRESH_MONTHS) -> List[str]:
    """
    Return a list of record IDs that have not been refreshed within `months` months.
    Uses last_refreshed_at if available, otherwise falls back to created_at.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    stale = []

    if not RECORDS_DIR.exists():
        return stale

    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        rec = load_record(record_id)
        if not rec or rec.state.archived:
            continue

        last_updated_str = rec.state.last_refreshed_at or rec.created_at
        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if last_updated < cutoff:
            stale.append(record_id)

    return stale


def archive_expired_records() -> Dict[str, Any]:
    """
    Scan all records and archive those whose retention_until has passed.
    Called by tools/retention_cli.py.
    """
    from .review import _archive_record

    results = {"archived": 0, "skipped": 0, "errors": []}
    now = datetime.now(timezone.utc)

    if not RECORDS_DIR.exists():
        return results

    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            rec = load_record(record_id)
            if not rec or rec.state.archived:
                results["skipped"] += 1
                continue

            if rec.compliance.retention_until:
                retention_date = datetime.fromisoformat(
                    rec.compliance.retention_until.replace("Z", "+00:00")
                )
                if now > retention_date:
                    _archive_record(record_id, reviewer="system_retention_job", reason="retention_expired")
                    results["archived"] += 1
                    continue

            results["skipped"] += 1
        except Exception as e:
            results["errors"].append({"record_id": record_id, "error": str(e)})

    return results
