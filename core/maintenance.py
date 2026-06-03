from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from .store import load_record, save_record
from .extract import extract_candidate_data
from .events import log_error
from .config import RECORDS_DIR, STALE_REFRESH_MONTHS, get_confidence_threshold
from .compliance import check_and_generate_review_cases
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


def bulk_refresh(updates: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Process a batch of candidate updates (simulating LinkedIn data pulls).
    `updates` is a list of dicts with 'record_id' and 'raw_text'. After updating
    each record this re-runs the compliance check, queueing any violations for
    human review. New skills / previous jobs are merged in without reordering or
    duplicating existing entries.
    """
    results: Dict[str, Any] = {"success": 0, "failed": 0, "errors": []}

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

            now = datetime.now(timezone.utc).isoformat() + "Z"
            record.updated_at = now
            record.state.last_refreshed_at = now

            if extraction.technologies_used:
                existing_skills = set(record.profile.technologies_used)
                for skill in extraction.technologies_used:
                    if skill not in existing_skills:
                        record.profile.technologies_used.append(skill)
                        existing_skills.add(skill)

            if extraction.previous_jobs:
                existing_jobs = set(record.profile.previous_jobs)
                for job in extraction.previous_jobs:
                    if job not in existing_jobs:
                        record.profile.previous_jobs.append(job)
                        existing_jobs.add(job)

            if extraction.summary:
                record.profile.summary = extraction.summary

            record.scores.extraction_confidence = extraction.extraction_confidence

            review_required = extraction.extraction_confidence < get_confidence_threshold()
            if review_required:
                record.compliance.human_review_required = True

            event = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "event_type": "bulk_refresh_update",
                "timestamp": now,
                "source": {"source_type": "linkedin_batch_export"},
                "actor": {"type": "system", "tool": "maintenance_bulk_refresh"},
                "model": model_info,
                "changes": [{"operation": "merge", "path": "/profile", "value": "updated_from_linkedin"}],
                "review": {
                    "required": review_required,
                    "reason": "low_extraction_confidence" if review_required else None,
                },
            }

            save_record(record_id, record, event=event)

            try:
                check_and_generate_review_cases(record_id, record)
            except Exception as comp_err:
                log_error({
                    "timestamp": now,
                    "stage": "post_bulk_refresh_compliance",
                    "record_id": record_id,
                    "error_type": "ComplianceCheckFailed",
                    "message": str(comp_err),
                })

            results["success"] += 1

        except Exception as e:
            results["failed"] += 1
            error_msg = str(e)
            results["errors"].append({"record_id": record_id, "error": error_msg})
            log_error({
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "stage": "bulk_refresh",
                "record_id": record_id,
                "error_type": "RefreshFailed",
                "message": error_msg,
            })

    return results


def find_stale_candidates(months: int = STALE_REFRESH_MONTHS) -> List[str]:
    """
    Return record IDs not refreshed within `months` months. Uses
    last_refreshed_at when available, else created_at.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    stale: List[str] = []

    if not RECORDS_DIR.exists():
        return stale

    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            rec = load_record(record_id)
        except Exception:
            continue
        if not rec or rec.state.archived:
            continue

        last_updated_str = rec.state.last_refreshed_at or rec.created_at
        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        if last_updated < cutoff:
            stale.append(record_id)

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
