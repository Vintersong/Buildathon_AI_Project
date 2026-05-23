import uuid
from datetime import datetime
from typing import Dict, Any, List

from .schemas import CandidateRecord
from .events import log_compliance
from .store import load_record
from .review import has_open_cases

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

    if not record.compliance.source:
        review_cases.append(_create_case(record_id, "missing_source"))

    if not record.compliance.retention_until:
        review_cases.append(_create_case(record_id, "missing_retention"))
        
    # 3. Data Region Check
    if record.compliance.data_region and record.compliance.data_region != "EEA":
        review_cases.append(_create_case(record_id, "data_region_violation"))
        
    # 4. Extraction Confidence
    if record.scores.extraction_confidence is not None and record.scores.extraction_confidence < 0.75:
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

def is_retention_expired(record: CandidateRecord) -> bool:
    if not record.compliance.retention_until:
        return False
    retention_date = datetime.fromisoformat(record.compliance.retention_until.replace("Z", "+00:00"))
    return datetime.now(retention_date.tzinfo) > retention_date

def record_block_reasons(record: CandidateRecord, record_id: str | None = None) -> List[str]:
    reasons = []
    if record.state.archived or record.state.status == "archived":
        reasons.append("archived")
    if record.state.stale:
        reasons.append("stale")
    if record.state.status == "pending_review" or record.compliance.human_review_required:
        reasons.append("pending_review")
    if record_id and has_open_cases(record_id):
        reasons.append("open_review_case")
    if not record.compliance.consent_basis:
        reasons.append("missing_consent")
    if not record.compliance.source:
        reasons.append("missing_source")
    if not record.compliance.retention_until:
        reasons.append("missing_retention")
    if is_retention_expired(record):
        reasons.append("retention_expired")
    if record.compliance.data_region and record.compliance.data_region != "EEA":
        reasons.append("data_region_violation")
    return reasons

def _create_case(record_id: str, reason: str) -> Dict[str, Any]:
    return {
        "case_id": f"review_{uuid.uuid4().hex[:12]}",
        "record_id": record_id,
        "reason": reason,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "open"
    }
