import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from filelock import FileLock

from .config import RECORDS_DIR, RECORD_INDEX_PATH
from .events import log_event
from .schemas import CandidateRecord
from .security import resolve_child_json

class SecurityError(Exception):
    pass

class StoreError(Exception):
    pass

def _resolve_record_path(record_id: str) -> Path:
    """Resolve and validate a record path to prevent path traversal."""
    try:
        return resolve_child_json(RECORDS_DIR, record_id, "record ID")
    except ValueError:
        raise SecurityError("Invalid record ID")

def load_record(record_id: str) -> Optional[CandidateRecord]:
    """Load a candidate record by ID."""
    path = _resolve_record_path(record_id)
    if not path.exists():
        return None
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return CandidateRecord(**data)

def save_record(record_id: str, record: CandidateRecord, event: Optional[Dict[str, Any]] = None):
    """Atomically save a record and optionally append a provenance event."""
    path = _resolve_record_path(record_id)
    lock = FileLock(f"{path}.lock")
    
    with lock:
        # 1. Write to .tmp file
        temp_path = path.with_suffix(".json.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(record.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
                
            # 2. Atomically rename .tmp to final path
            # On Windows, os.replace is atomic and replaces existing file
            os.replace(temp_path, path)
            
            # 3. Append event log if provided
            if event:
                # Add to record's provenance
                record.provenance.append(event)
                # Save again to include the event (simplified for this buildathon)
                # In a purely append-only event-sourcing setup, we'd do this cleaner
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(record.model_dump_json(indent=2))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, path)
                
                # Append to global JSONL log
                log_event(event)
                
            # 4. Update index
            _update_record_index(record_id, record)
            
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise StoreError(f"Failed to save record {record_id}: {str(e)}")

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
            "status": record.state.status,
            "updated_at": record.updated_at
        }
        
        # Write back to index (atomic write would be better here too, but acceptable for MVP)
        with open(RECORD_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
