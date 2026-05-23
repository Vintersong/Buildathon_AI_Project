from typing import List, Dict, Any
from datetime import datetime
import uuid

from .store import load_record, save_record
from .extract import extract_candidate_data
from .events import log_error

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
            
            # Update specific fields if they were found in the new text
            if extraction.technologies_used:
                # Merge unique
                record.profile.technologies_used = list(set(record.profile.technologies_used + extraction.technologies_used))
                
            if extraction.previous_jobs:
                 record.profile.previous_jobs = list(set(record.profile.previous_jobs + extraction.previous_jobs))
                 
            if extraction.summary:
                record.profile.summary = extraction.summary
                
            record.scores.extraction_confidence = extraction.extraction_confidence
            
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
                    "required": False
                }
            }
            
            # Save atomically
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
