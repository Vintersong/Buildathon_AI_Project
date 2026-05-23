import json
from pathlib import Path
from typing import List, Dict, Any
from filelock import FileLock

from .config import LOGS_DIR

REVIEW_QUEUE_PATH = LOGS_DIR / "review_queue.json"

def _ensure_queue():
    if not REVIEW_QUEUE_PATH.exists():
        with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)

def get_review_queue() -> List[Dict[str, Any]]:
    _ensure_queue()
    lock = FileLock(f"{REVIEW_QUEUE_PATH}.lock")
    with lock:
        try:
            with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

def get_open_cases(record_id: str) -> List[Dict[str, Any]]:
    return [
        case for case in get_review_queue()
        if case.get("record_id") == record_id and case.get("status") == "open"
    ]

def has_open_cases(record_id: str) -> bool:
    return bool(get_open_cases(record_id))

def add_to_queue(cases: List[Dict[str, Any]]):
    _ensure_queue()
    lock = FileLock(f"{REVIEW_QUEUE_PATH}.lock")
    with lock:
        with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
            queue = json.load(f)
            
        queue.extend(cases)
        
        with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)

def resolve_case(case_id: str, resolution: str, reviewer: str):
    _ensure_queue()
    resolved_record_id = None
    lock = FileLock(f"{REVIEW_QUEUE_PATH}.lock")
    with lock:
        with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
            queue = json.load(f)
            
        for case in queue:
            if case["case_id"] == case_id:
                case["status"] = "resolved"
                case["resolution"] = resolution
                case["reviewer"] = reviewer
                resolved_record_id = case.get("record_id")
                
        with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)

    if resolved_record_id and not has_open_cases(resolved_record_id):
        _clear_record_review_hold(resolved_record_id, reviewer)

def _clear_record_review_hold(record_id: str, reviewer: str):
    from datetime import datetime
    import uuid
    from .store import load_record, save_record

    record = load_record(record_id)
    if not record:
        return
    record.compliance.human_review_required = False
    if record.state.status == "pending_review":
        record.state.status = "reviewed"
    now = datetime.utcnow().isoformat() + "Z"
    record.updated_at = now
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "human_review_resolved",
        "timestamp": now,
        "source": {"source_type": "review_queue"},
        "actor": {"type": "human", "reviewer": reviewer},
        "changes": [{"operation": "replace", "path": "/compliance/human_review_required", "value": False}],
        "review": {"required": False}
    }
    save_record(record_id, record, event=event)
