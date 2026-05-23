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
    lock = FileLock(f"{REVIEW_QUEUE_PATH}.lock")
    with lock:
        with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
            queue = json.load(f)
            
        for case in queue:
            if case["case_id"] == case_id:
                case["status"] = "resolved"
                case["resolution"] = resolution
                case["reviewer"] = reviewer
                
        with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
