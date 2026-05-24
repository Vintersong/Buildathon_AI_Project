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
# AnonymizedResult shared dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnonymizedResult:
    anonymized_text: str
    mapping: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text-level PII anonymization (for raw CV / profile text sent to LLM)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}")
_LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w-]+/?")
_URL_RE = re.compile(r"https?://[^\s]+")
_WINDOWS_PATH_RE = re.compile(r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*')
_ADDRESS_TRIGGER_RE = re.compile(
    r"\b(?:Address|Street|Avenue|Blvd|Road|Lane|Drive|Str\.?|Str\s)\b",
    re.IGNORECASE,
)


def anonymize_candidate_text(text: str) -> AnonymizedResult:
    """
    Scan raw CV/profile text and replace direct identifiers with stable tokens.
    Returns the anonymized text and a reverse mapping so callers can rehydrate
    specific tokens after the LLM response.

    Tokens produced:
      CANDIDATE_001  — first/last name (best-effort from first non-trivial line)
      EMAIL_001+     — email addresses
      PHONE_001+     — phone numbers
      LINKEDIN_001   — LinkedIn profile URL
      URL_001+       — other URLs (portfolio, GitHub, etc.)
      PATH_001+      — local filesystem paths
      ADDR_LINE_001+ — lines that appear to be physical addresses
    """
    mapping: Dict[str, str] = {}
    result = text

    def _replace_all(pattern: re.Pattern, prefix: str, s: str) -> str:
        counter = [0]
        def _sub(m: re.Match) -> str:
            counter[0] += 1
            token = f"{prefix}_{counter[0]:03d}"
            mapping[token] = m.group(0)
            return token
        return pattern.sub(_sub, s)

    # 1. LinkedIn (before generic URL so it gets its own token)
    counter_li = [0]
    def _sub_li(m: re.Match) -> str:
        counter_li[0] += 1
        token = f"LINKEDIN_{counter_li[0]:03d}"
        mapping[token] = m.group(0)
        return token
    result = _LINKEDIN_RE.sub(_sub_li, result)

    # 2. Other URLs
    result = _replace_all(_URL_RE, "URL", result)

    # 3. Emails
    result = _replace_all(_EMAIL_RE, "EMAIL", result)

    # 4. Phone numbers
    result = _replace_all(_PHONE_RE, "PHONE", result)

    # 5. Windows-style file paths
    result = _replace_all(_WINDOWS_PATH_RE, "PATH", result)

    # 6. Address lines (replace the whole line)
    addr_counter = [0]
    def _sub_addr(m: re.Match) -> str:
        addr_counter[0] += 1
        token = f"ADDR_LINE_{addr_counter[0]:03d}"
        mapping[token] = m.group(0)
        return token
    result = _ADDRESS_TRIGGER_RE.sub(_sub_addr, result)

    # 7. Best-effort name: first non-empty, non-token line that looks like a
    #    proper name (2-5 title-cased words, no digits).
    name_token = "CANDIDATE_001"
    for line in result.splitlines():
        stripped = line.strip()
        if not stripped or any(t in stripped for t in mapping):
            continue
        parts = stripped.split()
        if (
            2 <= len(parts) <= 5
            and all(p[0].isupper() for p in parts if p)
            and not any(char.isdigit() for char in stripped)
        ):
            mapping[name_token] = stripped
            result = result.replace(stripped, name_token)
            break

    return AnonymizedResult(anonymized_text=result, mapping=mapping)


# ---------------------------------------------------------------------------
# Anonymization for outreach/rerank LLM prompts (record-object-based)
# ---------------------------------------------------------------------------

def anonymize_candidate_record(record: CandidateRecord, record_id: str) -> AnonymizedResult:
    """
    Build a PII-free text representation of a candidate for use in LLM prompts.
    Returns the anonymized text and a mapping so real values can be rehydrated
    only for fields the caller explicitly allows.
    """
    token = "CANDIDATE_001"
    real_name = record.identity.primary_name or record_id

    def _scrub(value: str | None) -> str:
        if not value:
            return ""
        return value.replace(real_name, token)

    skills = ", ".join(record.profile.technologies_used) if record.profile.technologies_used else "N/A"
    seniority = record.profile.seniority or "N/A"
    yoe = str(record.profile.years_of_experience) if record.profile.years_of_experience is not None else "N/A"
    summary = _scrub(record.profile.summary)
    location = _scrub(record.profile.location) or "N/A"
    degrees = ", ".join(record.profile.study_degrees) if record.profile.study_degrees else "N/A"
    jobs = _scrub(", ".join(record.profile.previous_jobs[:3])) if record.profile.previous_jobs else "N/A"

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


# ---------------------------------------------------------------------------
# Rehydration
# ---------------------------------------------------------------------------

def rehydrate_text(text: str, mapping: Dict[str, str], allowed: Set[str]) -> str:
    """
    Replace anonymization tokens back with real values, but only for token
    prefixes listed in `allowed`.

    When `allowed` contains full token keys (e.g. {"CANDIDATE_001"}) those
    are also matched directly, so callers can pass the mapping keys themselves.

    Example: allowed={"CANDIDATE"} rehydrates CANDIDATE_001 -> real name,
    but leaves JOB_001 unreplaced.
    """
    for token, real_value in mapping.items():
        prefix = token.split("_")[0]
        if prefix in allowed or token in allowed:
            text = text.replace(token, real_value)
    return text
