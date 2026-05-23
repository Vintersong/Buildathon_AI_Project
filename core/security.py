"""Security utilities: PII redaction, anonymization, rehydration."""
from dataclasses import dataclass, field
from typing import Dict, Set
import re

from .schemas import CandidateRecord

# ---------------------------------------------------------------------------
# PII redaction for event/audit logs
# ---------------------------------------------------------------------------

_PII_KEYS = {
    "primary_name", "emails", "phones", "linkedin_url",
    "name", "email", "phone",
}

def redact_pii(data: dict) -> dict:
    """Recursively redact known PII keys from a dict before writing to logs."""
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if k in _PII_KEYS:
            if isinstance(v, list):
                result[k] = ["[REDACTED]" for _ in v]
            elif v is not None:
                result[k] = "[REDACTED]"
            else:
                result[k] = v
        elif isinstance(v, dict):
            result[k] = redact_pii(v)
        elif isinstance(v, list):
            result[k] = [redact_pii(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Anonymization for outreach LLM prompt (keeps no real PII in the prompt)
# ---------------------------------------------------------------------------

@dataclass
class AnonymizedResult:
    anonymized_text: str
    mapping: Dict[str, str] = field(default_factory=dict)


def anonymize_candidate_record(record: CandidateRecord, record_id: str) -> AnonymizedResult:
    """
    Build a PII-free text representation of a candidate for use in LLM prompts.
    Returns the anonymized text and a mapping so real values can be rehydrated
    only for fields the caller explicitly allows.
    """
    token = "CANDIDATE_001"
    real_name = record.identity.primary_name or record_id

    skills = ", ".join(record.profile.technologies_used) if record.profile.technologies_used else "N/A"
    seniority = record.profile.seniority or "N/A"
    yoe = str(record.profile.years_of_experience) if record.profile.years_of_experience is not None else "N/A"
    summary = record.profile.summary or ""
    location = record.profile.location or "N/A"
    degrees = ", ".join(record.profile.study_degrees) if record.profile.study_degrees else "N/A"
    jobs = ", ".join(record.profile.previous_jobs[:3]) if record.profile.previous_jobs else "N/A"

    text = (
        f"Candidate: {token}\n"
        f"Seniority: {seniority} ({yoe} years)\n"
        f"Location: {location}\n"
        f"Education: {degrees}\n"
        f"Skills: {skills}\n"
        f"Previous roles: {jobs}\n"
        f"Summary: {summary}"
    )

    return AnonymizedResult(
        anonymized_text=text,
        mapping={token: real_name},
    )


def rehydrate_text(text: str, mapping: Dict[str, str], allowed: Set[str]) -> str:
    """
    Replace anonymization tokens back with real values, but only for token
    prefixes listed in `allowed`.

    Example: allowed={"CANDIDATE"} will rehydrate CANDIDATE_001 -> real name,
    but will leave JOB_001 unreplaced.
    """
    for token, real_value in mapping.items():
        prefix = token.split("_")[0]
        if prefix in allowed:
            text = text.replace(token, real_value)
    return text
