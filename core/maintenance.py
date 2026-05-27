from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from .store import load_record, save_record
from .config import RECORDS_DIR, STALE_REFRESH_MONTHS
from .schemas import CandidateRecord


def _months_since(iso_date: str) -> float:
    """Return the number of months between now and the given ISO timestamp."""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.days / 30.44
    except (ValueError, TypeError):
        return 0.0


def flag_stale_records(stale_months: int = STALE_REFRESH_MONTHS) -> List[Dict[str, Any]]:
    """
    Scan all candidate records and return a list of records that haven't been
    updated in more than `stale_months` months.
    """
    if not RECORDS_DIR.exists():
        return []

    stale = []
    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            record = load_record(record_id)
        except Exception:
            continue

        if record.state and record.state.archived:
            continue

        months_old = _months_since(record.updated_at or record.created_at)
        if months_old >= stale_months:
            stale.append({
                "record_id": record_id,
                "name": record.identity.primary_name or "Unknown",
                "updated_at": record.updated_at,
                "months_since_update": round(months_old, 1),
            })

    stale.sort(key=lambda r: r["months_since_update"], reverse=True)
    return stale


def archive_record(record_id: str, reason: str = "manual") -> Dict[str, Any]:
    """
    Mark a candidate record as archived. Archived records are excluded from
    matching and compliance scans but are retained for audit purposes.
    """
    record = load_record(record_id)
    if record.state and record.state.archived:
        return {"record_id": record_id, "status": "already_archived"}

    now = datetime.now(timezone.utc).isoformat()
    record.state.archived = True
    record.state.archived_at = now
    record.state.archived_reason = reason
    record.updated_at = now

    event = {
        "timestamp": now,
        "event": "record_archived",
        "reason": reason,
    }
    save_record(record_id, record, event=event)
    return {"record_id": record_id, "status": "archived", "archived_at": now}


def restore_record(record_id: str) -> Dict[str, Any]:
    """
    Unarchive a previously archived record, returning it to active status.
    """
    record = load_record(record_id)
    if not (record.state and record.state.archived):
        return {"record_id": record_id, "status": "not_archived"}

    now = datetime.now(timezone.utc).isoformat()
    record.state.archived = False
    record.state.archived_at = None
    record.state.archived_reason = None
    record.updated_at = now

    event = {
        "timestamp": now,
        "event": "record_restored",
    }
    save_record(record_id, record, event=event)
    return {"record_id": record_id, "status": "restored", "restored_at": now}


def purge_expired_records() -> List[Dict[str, Any]]:
    """
    Permanently delete records whose `retention_until` date has passed.
    This is a destructive operation - call only from scheduled GDPR maintenance jobs.
    """
    if not RECORDS_DIR.exists():
        return []

    purged = []
    now = datetime.now(timezone.utc)

    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            record = load_record(record_id)
        except Exception:
            continue

        retention = record.compliance.retention_until
        if not retention:
            continue

        try:
            retention_dt = datetime.fromisoformat(retention.replace("Z", "+00:00"))
        except ValueError:
            continue

        if now >= retention_dt:
            path.unlink(missing_ok=True)
            lock_path = path.with_suffix(".json.lock")
            lock_path.unlink(missing_ok=True)
            purged.append({
                "record_id": record_id,
                "name": record.identity.primary_name or "Unknown",
                "retention_until": retention,
                "purged_at": now.isoformat(),
            })

    return purged
