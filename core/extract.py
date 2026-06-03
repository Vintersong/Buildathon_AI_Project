import json
import re
from typing import Dict, Any
import google.generativeai as genai
from pydantic import ValidationError
from datetime import datetime
import uuid

from .config import QUARANTINE_DIR, get_use_local_llm, LM_STUDIO_MODEL, LM_STUDIO_BASE_URL
from .schemas import CandidateExtraction
from .security import anonymize_candidate_text, rehydrate_text

# Feature flag — when False the external LLM call is skipped and the
# heuristic fallback is used instead (safe for air-gapped / no-key deploys).
import os
from .config import GEMINI_API_KEY, get_active_api_key, get_active_model, ENABLE_EXTERNAL_LLM

DEFAULT_EXTRACT_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# LM Studio helpers (used by web/app.py chat endpoint)
# ---------------------------------------------------------------------------

def _configure_genai() -> bool:
    """Configure Gemini with the currently-active key. Returns True on success."""
    key = get_active_api_key()
    if not key:
        return False
    genai.configure(api_key=key)
    return True


def _lm_studio_available() -> bool:
    """Return True if the configured LM Studio server is reachable."""
    import urllib.request
    models_url = LM_STUDIO_BASE_URL.rstrip("/") + "/models"
    try:
        urllib.request.urlopen(models_url, timeout=1)
        return True
    except Exception:
        return False


# Minimal json_schema schemas for LM Studio's response_format
# LM Studio only accepts 'json_schema' or 'text' — 'json_object' is not supported.
_RERANK_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "rerank_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "match_score": {"type": "number"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "uncertainty_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["match_score", "evidence", "uncertainty_flags"],
            "additionalProperties": False,
        },
    },
}

_EXTRACTION_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "candidate_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "linkedin_url": {"type": ["string", "null"]},
                "headline": {"type": ["string", "null"]},
                "summary": {"type": ["string", "null"]},
                "seniority": {"type": ["string", "null"]},
                "years_of_experience": {"type": ["number", "null"]},
                "technologies_used": {"type": "array", "items": {"type": "string"}},
                "previous_jobs": {"type": "array", "items": {"type": "string"}},
                "study_degrees": {"type": "array", "items": {"type": "string"}},
                "languages_spoken": {"type": "array", "items": {"type": "string"}},
                "location": {"type": ["string", "null"]},
                "projects_developed": {"type": "array", "items": {"type": "string"}},
                "extraction_confidence": {"type": "number"},
                "sensitive_data_detected": {"type": "boolean"},
            },
            "required": [
                "name", "emails", "phones", "linkedin_url", "headline", "summary",
                "seniority", "years_of_experience", "technologies_used", "previous_jobs",
                "study_degrees", "languages_spoken", "location", "projects_developed",
                "extraction_confidence", "sensitive_data_detected",
            ],
            "additionalProperties": False,
        },
    },
}


def _lm_studio_chat(messages: list, json_mode: bool = True) -> str:
    """Send a chat completion request to the local LM Studio server."""
    import urllib.request
    payload: dict = {
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": 0.1,
    }
    if json_mode:
        payload["response_format"] = _EXTRACTION_JSON_SCHEMA
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LM_STUDIO_BASE_URL.rstrip("/") + "/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def _lm_studio_rerank(messages: list) -> str:
    """Send a rerank request to the local LM Studio server with rerank JSON schema."""
    import urllib.request
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "response_format": _RERANK_JSON_SCHEMA,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LM_STUDIO_BASE_URL.rstrip("/") + "/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


_EXTRACTION_SYSTEM_PROMPT = (
    "You are an expert HR data extractor. Extract structured candidate information "
    "from the provided text. The text has been anonymized — tokens like CANDIDATE_001 "
    "represent real names. Return only valid JSON matching the schema exactly."
)


def _extraction_prompt(anonymized_text: str) -> str:
    return (
        "Extract all candidate information from this anonymized CV/profile text.\n\n"
        f"{anonymized_text}\n\n"
        "Return a JSON object with these exact fields: name (string or null), "
        "emails (array), phones (array), linkedin_url (string or null), "
        "headline (string or null), summary (string or null), "
        "seniority (string or null, one of: Intern/Junior/Mid/Senior/Lead), "
        "years_of_experience (number or null), technologies_used (array), "
        "previous_jobs (array), study_degrees (array), languages_spoken (array), "
        "location (string or null), projects_developed (array), "
        "extraction_confidence (0.0-1.0), sensitive_data_detected (boolean)."
    )


def extract_candidate_data(text: str) -> tuple["CandidateExtraction", Dict[str, Any]]:
    """
    Extract structured candidate data from raw CV/profile text.

    When ENABLE_EXTERNAL_LLM is True and the active provider is reachable:
    anonymises PII, sends to the configured LLM, then rehydrates the name token
    so the record stores the real name. Otherwise falls back to heuristic
    extraction (always available, no key required).
    """
    from . import llm
    from .config import get_active_provider

    if not ENABLE_EXTERNAL_LLM or not llm.llm_available():
        return extract_candidate_data_heuristic(text)

    anon = anonymize_candidate_text(text)
    messages = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": _extraction_prompt(anon.anonymized_text)},
    ]

    try:
        raw = llm.complete(messages, json_mode=True)
        data = json.loads(raw)
        extraction = CandidateExtraction(**data)

        # Rehydrate only the name token
        if extraction.name:
            extraction.name = rehydrate_text(extraction.name, anon.mapping, allowed={"CANDIDATE"})

        return extraction, {"model": llm.active_model(), "provider": get_active_provider()}

    except (json.JSONDecodeError, ValidationError) as e:
        _quarantine_failed_extraction(text, str(e))
        return extract_candidate_data_heuristic(text)
    except Exception as e:
        print(f"[extract] LLM extraction failed: {e}")
        return extract_candidate_data_heuristic(text)


def extract_candidate_data_heuristic(text: str) -> tuple["CandidateExtraction", Dict[str, Any]]:
    """
    Heuristic fallback extractor — no LLM required.
    Used when ENABLE_EXTERNAL_LLM is False or GEMINI_API_KEY is absent.
    Quality is lower but always available.
    """
    import re as _re

    email_re = _re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
    phone_re = _re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}")
    linkedin_re = _re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w-]+/?")

    emails = list(dict.fromkeys(email_re.findall(text)))
    phones = list(dict.fromkeys(phone_re.findall(text)))
    linkedin_urls = linkedin_re.findall(text)
    linkedin_url = linkedin_urls[0] if linkedin_urls else None

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = None
    for line in lines[:10]:
        parts = line.split()
        if (
            2 <= len(parts) <= 4
            and all(p[0].isupper() for p in parts if p)
            and not any(c.isdigit() for c in line)
            and "@" not in line
        ):
            name = line
            break

    tech_keywords = [
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
        "react", "vue", "angular", "node", "django", "fastapi", "flask", "spring",
        "sql", "postgresql", "mysql", "mongodb", "redis", "docker", "kubernetes",
        "aws", "azure", "gcp", "git", "linux", "machine learning", "tensorflow",
        "pytorch", "scikit-learn", "pandas", "numpy",
    ]
    text_lower = text.lower()
    technologies = [t for t in tech_keywords if t in text_lower]

    filled = sum([
        bool(name), bool(emails), bool(technologies), bool(linkedin_url)
    ])
    confidence = round(min(0.35 + filled * 0.10, 0.65), 2)

    return (
        CandidateExtraction(
            name=name,
            emails=emails,
            phones=phones,
            linkedin_url=linkedin_url,
            headline=None,
            summary=None,
            seniority=None,
            years_of_experience=None,
            technologies_used=technologies,
            previous_jobs=[],
            study_degrees=[],
            languages_spoken=[],
            location=None,
            projects_developed=[],
            extraction_confidence=confidence,
            sensitive_data_detected=False,
        ),
        {"model": "heuristic", "provider": "local"},
    )


def _quarantine_failed_extraction(text: str, reason: str):
    quarantine_id = f"ext_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    folder = QUARANTINE_DIR / "extraction_failures"
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{quarantine_id}.txt", "w", encoding="utf-8") as f:
        f.write(f"Reason: {reason}\n\n{text}")
