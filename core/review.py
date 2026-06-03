import json
from pathlib import Path
from typing import List, Dict, Any
from filelock import FileLock

from .config import LOGS_DIR, RECORDS_DIR
from .store import load_record, save_record
from .schemas import CandidateRecord

REVIEW_QUEUE_PATH = LOGS_DIR / "review_queue.jsonl"


def _create_case(record_id: str, reason: str) -> Dict[str, Any]:
    from datetime import datetime, timezone
    import uuid
    return {
        "case_id": f"rv_{uuid.uuid4().hex[:10]}",
        "record_id": record_id,
        "reason": reason,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        "resolved_at": None,
        "resolved_by": None,
        "notes": None,
    }


def append_review_case(case: Dict[str, Any]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(REVIEW_QUEUE_PATH) + ".lock")
    with lock:
        with open(REVIEW_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(case) + "\n")


def get_open_review_cases() -> List[Dict[str, Any]]:
    if not REVIEW_QUEUE_PATH.exists():
        return []
    cases = []
    with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
                if case.get("status") == "open":
                    cases.append(case)
            except json.JSONDecodeError:
                continue
    return cases


def get_all_review_cases() -> List[Dict[str, Any]]:
    if not REVIEW_QUEUE_PATH.exists():
        return []
    cases = []
    with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


def resolve_case(
    case_id: str,
    resolved_by: str = "system",
    notes: str = "",
    resolution: str = "approved",
) -> Dict[str, Any]:
    """
    Resolve a single review case by case_id.

    When resolution == 'purged', also closes all other open cases on the same
    record (since the record will be deleted). For all other resolutions, only
    the targeted case is resolved.
    """
    from datetime import datetime, timezone

    if not REVIEW_QUEUE_PATH.exists():
        return {"error": "Review queue not found"}

    all_cases = get_all_review_cases()
    target = next((c for c in all_cases if c["case_id"] == case_id), None)
    if not target:
        return {"error": f"Case {case_id} not found"}

    now = datetime.now(timezone.utc).isoformat() + "Z"
    record_id = target["record_id"]
    updated = []

    for case in all_cases:
        if case["case_id"] == case_id:
            case["status"] = "resolved"
            case["resolved_at"] = now
            case["resolved_by"] = resolved_by
            case["notes"] = notes
            case["resolution"] = resolution
        elif (
            resolution == "purged"
            and case["record_id"] == record_id
            and case["status"] == "open"
        ):
            # On purge only: close sibling cases so the record can be deleted cleanly
            case["status"] = "resolved"
            case["resolved_at"] = now
            case["resolved_by"] = "system"
            case["notes"] = "Auto-closed: parent record purged"
            case["resolution"] = "purged"
        updated.append(case)

    lock = FileLock(str(REVIEW_QUEUE_PATH) + ".lock")
    with lock:
        with open(REVIEW_QUEUE_PATH, "w", encoding="utf-8") as f:
            for case in updated:
                f.write(json.dumps(case) + "\n")

    return {"case_id": case_id, "status": "resolved", "resolution": resolution}


def get_review_cases_for_record(record_id: str) -> List[Dict[str, Any]]:
    return [c for c in get_all_review_cases() if c["record_id"] == record_id]


# ---------------------------------------------------------------------------
# Backwards-compatibility helpers (used by web/app.py)
# ---------------------------------------------------------------------------

def get_review_queue() -> List[Dict[str, Any]]:
    """Return every review case (open + resolved). Legacy alias used by the API."""
    return get_all_review_cases()


def add_to_queue(cases: List[Dict[str, Any]]) -> None:
    """Append one or more cases to the review queue (legacy list-based API)."""
    for case in cases:
        append_review_case(case)


def has_open_cases(record_id: str) -> bool:
    """True when the record has at least one open review case."""
    return any(c.get("record_id") == record_id for c in get_open_review_cases())


def _clear_record_review_hold(record_id: str, reviewer: str) -> None:
    """Lift the human-review hold on a record once its cases are resolved."""
    from datetime import datetime, timezone
    import uuid

    record = load_record(record_id)
    if not record:
        return
    record.compliance.human_review_required = False
    if record.state.status == "pending_review":
        record.state.status = "reviewed"
    now = datetime.now(timezone.utc).isoformat() + "Z"
    record.updated_at = now
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "event_type": "human_review_resolved",
        "timestamp": now,
        "source": {"source_type": "review_queue"},
        "actor": {"type": "human", "reviewer": reviewer},
        "changes": [{"operation": "replace", "path": "/compliance/human_review_required", "value": False}],
        "review": {"required": False},
    }
    save_record(record_id, record, event=event)
