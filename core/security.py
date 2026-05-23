import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
LINKEDIN_RE = re.compile(r"https?://(?:[\w]+\.)?linkedin\.com/[^\s)>\"]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)
WINDOWS_PATH_RE = re.compile(r"(?<!\w)[A-Za-z]:\\[^\r\n\t<>|?*]+")
UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:[\w .-]+/)+[\w .-]+")
ADDRESS_LINE_RE = re.compile(r"(?im)^(?:address|contact)\s*[:\-].*$")

@dataclass
class AnonymizedPayload:
    anonymized_text: str
    mapping: dict[str, str] = field(default_factory=dict)
    redacted_types: list[str] = field(default_factory=list)

def redact_pii(value: Any) -> Any:
    """Recursively redact obvious PII from log/quarantine payloads."""
    if isinstance(value, str):
        value = EMAIL_RE.sub("[redacted-email]", value)
        return PHONE_RE.sub("[redacted-phone]", value)
    if isinstance(value, list):
        return [redact_pii(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_pii(item) for key, item in value.items()}
    return value

def anonymize_candidate_text(text: str, candidate_id: str | None = None) -> AnonymizedPayload:
    """Replace direct identifiers in free text before it is sent to an external API."""
    anonymizer = _Anonymizer(text or "")
    anonymizer.replace_regex("LINKEDIN", LINKEDIN_RE)
    anonymizer.replace_regex("EMAIL", EMAIL_RE)
    anonymizer.replace_regex("PHONE", PHONE_RE)
    anonymizer.replace_regex("FILE", WINDOWS_PATH_RE)
    anonymizer.replace_regex("FILE", UNIX_PATH_RE)
    anonymizer.replace_regex("URL", URL_RE)
    anonymizer.replace_regex("ADDRESS", ADDRESS_LINE_RE)

    guessed_name = _guess_candidate_name(text or "")
    if guessed_name:
        anonymizer.replace_literal("CANDIDATE", guessed_name)
    elif candidate_id:
        anonymizer.mapping.setdefault("CANDIDATE_001", "candidate")
        anonymizer._mark_type("CANDIDATE")

    return anonymizer.payload()

def anonymize_candidate_record(record: Any, record_id: str) -> AnonymizedPayload:
    """Build an anonymized professional profile from a CandidateRecord."""
    candidate_name = getattr(getattr(record, "identity", None), "primary_name", None) or "candidate"
    mapping = {"CANDIDATE_001": candidate_name}
    profile = getattr(record, "profile", None)
    lines = [
        "Candidate: CANDIDATE_001",
        f"Headline: {getattr(profile, 'headline', None) or ''}",
        f"Summary: {getattr(profile, 'summary', None) or ''}",
        f"Seniority: {getattr(profile, 'seniority', None) or ''}",
        f"Years of experience: {getattr(profile, 'years_of_experience', None) or ''}",
        f"Degrees: {', '.join(getattr(profile, 'study_degrees', []) or [])}",
        f"Skills: {', '.join(getattr(profile, 'technologies_used', []) or [])}",
        f"Languages: {', '.join(getattr(profile, 'languages_spoken', []) or [])}",
        f"Location: {getattr(profile, 'location', None) or ''}",
        f"Previous jobs: {', '.join(getattr(profile, 'previous_jobs', []) or [])}",
        f"Projects: {', '.join(getattr(profile, 'projects_developed', []) or [])}",
    ]
    payload = anonymize_candidate_text("\n".join(lines), record_id)
    payload.anonymized_text = re.sub(re.escape(candidate_name), "CANDIDATE_001", payload.anonymized_text)
    payload.mapping.update(mapping)
    if "CANDIDATE" not in payload.redacted_types:
        payload.redacted_types.append("CANDIDATE")
    return payload

def rehydrate_text(text: str, mapping: dict[str, str], allowed: set[str] | None = None) -> str:
    """Restore selected placeholders locally after an external response returns."""
    result = text or ""
    for placeholder, original in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        placeholder_type = placeholder.split("_", 1)[0]
        if allowed is not None and placeholder_type not in allowed:
            continue
        result = result.replace(placeholder, original)
    return result

def validate_simple_id(value: str, label: str = "identifier") -> str:
    if not value or "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"Invalid {label}")
    return value

def resolve_child_json(base_dir: Path, item_id: str, label: str) -> Path:
    validate_simple_id(item_id, label)
    base = base_dir.resolve()
    path = (base_dir / f"{item_id}.json").resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"Path traversal attempt detected for {label}")
    return path

class _Anonymizer:
    def __init__(self, text: str):
        self.text = text
        self.mapping: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._types: list[str] = []

    def replace_regex(self, placeholder_type: str, pattern: re.Pattern):
        def repl(match: re.Match) -> str:
            return self._placeholder(placeholder_type, match.group(0))
        self.text = pattern.sub(repl, self.text)

    def replace_literal(self, placeholder_type: str, value: str):
        if not value:
            return
        placeholder = self._placeholder(placeholder_type, value)
        self.text = re.sub(re.escape(value), placeholder, self.text)

    def payload(self) -> AnonymizedPayload:
        return AnonymizedPayload(
            anonymized_text=self.text,
            mapping=self.mapping,
            redacted_types=self._types[:],
        )

    def _placeholder(self, placeholder_type: str, value: str) -> str:
        for placeholder, original in self.mapping.items():
            if original == value and placeholder.startswith(f"{placeholder_type}_"):
                self._mark_type(placeholder_type)
                return placeholder
        next_index = self._counters.get(placeholder_type, 0) + 1
        self._counters[placeholder_type] = next_index
        placeholder = f"{placeholder_type}_{next_index:03d}"
        self.mapping[placeholder] = value
        self._mark_type(placeholder_type)
        return placeholder

    def _mark_type(self, placeholder_type: str):
        if placeholder_type not in self._types:
            self._types.append(placeholder_type)

def _guess_candidate_name(text: str) -> str | None:
    for line in text.splitlines()[:8]:
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in stripped.lower() for token in ["@", "linkedin", "github", "http", "curriculum", "resume", "cv", "address", "phone"]):
            continue
        words = re.findall(r"[A-Z][a-zA-Z'-]+", stripped)
        if 2 <= len(words) <= 4 and len(stripped) <= 80:
            return " ".join(words)
    return None
