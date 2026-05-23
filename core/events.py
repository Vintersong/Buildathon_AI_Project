import json
from typing import Dict, Any
from .config import EVENTS_LOG_PATH, ERRORS_LOG_PATH, COMPLIANCE_LOG_PATH

def append_jsonl(file_path, data: Dict[str, Any]):
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

def log_event(event_data: Dict[str, Any]):
    append_jsonl(EVENTS_LOG_PATH, event_data)

def log_error(error_data: Dict[str, Any]):
    append_jsonl(ERRORS_LOG_PATH, error_data)

def log_compliance(compliance_data: Dict[str, Any]):
    append_jsonl(COMPLIANCE_LOG_PATH, compliance_data)
