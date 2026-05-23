from typing import List, Dict, Any
from datetime import datetime, timedelta
import uuid

from .store import load_record, save_record
from .extract import extract_candidate_data
from .events import log_error
from .config import DEFAULT_RETENTION_DAYS, DEFAULT_DATA_REGION, DEFAULT_CONSENT_BASIS
from .compliance import evaluate_compliance, is_retention_expired
from .review import add_to_queue

def bulk_refresh(updates: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Process a batch of candidate updates (simulating LinkedIn data pulls).
    `updates` is a list of dictionaries with 'record_id' and 'raw_text'.
    """
    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }
    
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
            # Extract new data from the provided text
            extraction, model_info = extract_candidate_data(raw_text)
            
            # Merge logic (simplified for buildathon, typically you'd do deep merge and compare)
            now = datetime.utcnow().isoformat() + "Z"
            record.updated_at = now
            record.state.last_refreshed_at = now
            
            # Update specific fields if they were found in the new text
            if extraction.technologies_used:
                _append_unique(record.profile.technologies_used, extraction.technologies_used)
                
            if extraction.previous_jobs:
                _append_unique(record.profile.previous_jobs, extraction.previous_jobs)
                 
            if extraction.summary:
                record.profile.summary = extraction.summary
                
            record.scores.extraction_confidence = extraction.extraction_confidence
            if not record.compliance.source:
                record.compliance.source = "linkedin_batch_export"
            if not record.compliance.retention_until:
                record.compliance.retention_until = (
                    datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)
                ).isoformat() + "Z"
            if not record.compliance.data_region:
                record.compliance.data_region = DEFAULT_DATA_REGION
            if not record.compliance.consent_basis and DEFAULT_CONSENT_BASIS:
                record.compliance.consent_basis = DEFAULT_CONSENT_BASIS
            review_required = (
                extraction.extraction_confidence < 0.75
                or bool(extraction.review_flags)
                or bool(model_info.get("external"))
                or not record.compliance.consent_basis
            )
            if review_required:
                record.compliance.human_review_required = True
                record.state.status = "pending_review"
            
            # Provenance Event
            event = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "event_type": "bulk_refresh_update",
                "timestamp": now,
                "source": {
                    "source_type": "linkedin_batch_export"
                },
                "actor": {
                    "type": "system",
                    "tool": "maintenance_bulk_refresh"
                },
                "model": model_info,
                "changes": [{"operation": "merge", "path": "/profile", "value": "updated_from_linkedin"}],
                "review": {
                    "required": review_required,
                    "reason": ",".join(extraction.review_flags) if review_required else None
                }
            }
            
            # Save atomically
            save_record(record_id, record, event=event)
            review_cases = evaluate_compliance(record_id)
            if review_cases:
                add_to_queue(review_cases)
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

def archive_expired_records() -> Dict[str, Any]:
    """Archive records past their retention date without deleting files."""
    from .config import RECORDS_DIR

    archived = []
    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        record = load_record(record_id)
        if not record or not is_retention_expired(record):
            continue
        if record.state.archived or record.state.status == "archived":
            continue
        now = datetime.utcnow().isoformat() + "Z"
        record.updated_at = now
        record.state.archived = True
        record.state.status = "archived"
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "event_type": "retention_archive",
            "timestamp": now,
            "source": {"source_type": "retention_policy"},
            "actor": {"type": "system", "tool": "maintenance_retention_archive"},
            "changes": [{"operation": "replace", "path": "/state/status", "value": "archived"}],
            "review": {"required": False}
        }
        save_record(record_id, record, event=event)
        archived.append(record_id)
    return {"archived": len(archived), "record_ids": archived}

def _append_unique(target: list, incoming: list):
    for item in incoming or []:
        if item not in target:
            target.append(item)
