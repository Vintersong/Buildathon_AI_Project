import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from .config import COMPLIANCE_LOG_PATH, LOGS_DIR, get_confidence_threshold
from .schemas import CandidateRecord
from .time_utils import utc_now_iso


def log_compliance(event: Dict[str, Any]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMPLIANCE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{__import__('json').dumps(event)}\n")


def record_block_reasons(record: CandidateRecord) -> List[str]:
    """
    Return a list of reasons why this record should be blocked from matching.
    Empty list = record is eligible.
    """
    reasons = []
    if record.compliance.consent_withdrawn:
        reasons.append("consent_withdrawn")
    retention = record.compliance.retention_until
    if retention:
        try:
            retention_dt = datetime.fromisoformat(retention.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= retention_dt:
                reasons.append("retention_expired")
        except ValueError:
            pass
    return reasons


def check_and_generate_review_cases(
    record_id: str,
    record: CandidateRecord,
) -> List[Dict[str, Any]]:
    """
    Inspect the record for compliance issues and create review cases as needed.
    Returns the list of cases created.
    """
    from .review import append_review_case

    review_cases = []

    # 1. Consent withdrawn
    if record.compliance.consent_withdrawn:
        review_cases.append(_create_case(record_id, "consent_withdrawn"))

    # 2. Retention expired
    if record.compliance.retention_until:
        try:
            retention_dt = datetime.fromisoformat(
                record.compliance.retention_until.replace("Z", "+00:00")
            )
            if datetime.now(timezone.utc) >= retention_dt:
                review_cases.append(_create_case(record_id, "retention_expired"))
        except ValueError:
            pass

    # 3. Non-EEA data region — normalise before comparing so 'eu', 'EU', 'eea' all pass
    data_region = (record.compliance.data_region or "").strip().upper()
    if data_region and data_region not in ("EEA", "EU"):
        review_cases.append(_create_case(record_id, "data_region_violation"))

    # 4. Extraction Confidence
    if (
        record.scores.extraction_confidence is not None
        and record.scores.extraction_confidence < get_confidence_threshold()
    ):
        review_cases.append(_create_case(record_id, "low_extraction_confidence"))

    # 5. Sensitive Data
    if record.compliance.sensitive_data_detected:
        review_cases.append(_create_case(record_id, "sensitive_data_detected"))

    if review_cases:
        log_compliance({
            "timestamp": utc_now_iso(),
            "record_id": record_id,
            "cases_generated": len(review_cases),
            "reasons": [c["reason"] for c in review_cases]
        })

    for case in review_cases:
        append_review_case(case)

    return review_cases


def _create_case(record_id: str, reason: str) -> Dict[str, Any]:
    return {
        "case_id": f"rv_{uuid.uuid4().hex[:10]}",
        "record_id": record_id,
        "reason": reason,
        "status": "open",
        "created_at": utc_now_iso(),
        "resolved_at": None,
        "resolved_by": None,
        "notes": None,
    }
