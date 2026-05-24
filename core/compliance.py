import uuid
from datetime import datetime
from typing import Dict, Any, List

from .config import COMPLIANCE_LOG_PATH
from .schemas import CandidateRecord
from .events import log_compliance
from .store import load_record
from .config import get_confidence_threshold


def evaluate_compliance(record_id: str) -> List[Dict[str, Any]]:
    """
    Run deterministic GDPR/compliance policy checks.
    Returns a list of review cases if violations or uncertain states are found.
    """
    record = load_record(record_id)
    if not record:
        return []

    review_cases = []

    # 1. Retention Check
    if record.compliance.retention_until:
        retention_date = datetime.fromisoformat(record.compliance.retention_until.replace("Z", "+00:00"))
        if datetime.now(retention_date.tzinfo) > retention_date:
            review_cases.append(_create_case(record_id, "retention_expired"))

    # 2. Consent Check
    if not record.compliance.consent_basis:
        review_cases.append(_create_case(record_id, "missing_consent"))

    # 3. Data Region Check — only flag if explicitly set to a non-EEA value.
    #    None / missing means unknown; treat as acceptable to avoid false positives.
    if record.compliance.data_region and record.compliance.data_region != "EEA":
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
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "record_id": record_id,
            "cases_generated": len(review_cases),
            "reasons": [c["reason"] for c in review_cases]
        })

    return review_cases


def record_block_reasons(record: CandidateRecord, record_id: str) -> List[str]:
    """
    Return a list of reasons that should block outreach to this candidate.
    An empty list means outreach is permitted.
    """
    reasons = []
    if record.state.archived:
        reasons.append("archived")
    if not record.compliance.consent_basis:
        reasons.append("missing_consent")
    if "do_not_contact" in record.state.tags:
        reasons.append("do_not_contact_tag")
    if record.compliance.redaction_required:
        reasons.append("redaction_required")
    # Block if retention period has legally expired
    if record.compliance.retention_until:
        try:
            retention_date = datetime.fromisoformat(
                record.compliance.retention_until.replace("Z", "+00:00")
            )
            if datetime.now(retention_date.tzinfo) > retention_date:
                reasons.append("retention_expired")
        except ValueError:
            # Malformed date — treat as a block to be safe
            reasons.append("retention_date_invalid")
    return reasons


def _create_case(record_id: str, reason: str) -> Dict[str, Any]:
    return {
        "case_id": f"review_{uuid.uuid4().hex[:12]}",
        "record_id": record_id,
        "reason": reason,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "open"
    }
