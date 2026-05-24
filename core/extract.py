import json
import re
from typing import Dict, Any, Tuple
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
from .config import GEMINI_API_KEY, get_active_api_key, get_active_model

ENABLE_EXTERNAL_LLM = os.getenv("ENABLE_EXTERNAL_LLM", "true").lower() == "true"

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
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "emails": {"type": "array", "items": {"type": "string"}},
                "phones": {"type": "array", "items": {"type": "string"}},
                "linkedin_url": {"type": ["string", "null"]},
                "seniority": {"type": ["string", "null"]},
                "years_of_experience": {"type": ["integer", "null"]},
                "study_degrees": {"type": "array", "items": {"type": "string"}},
                "technologies_used": {"type": "array", "items": {"type": "string"}},
                "languages_spoken": {"type": "array", "items": {"type": "string"}},
                "location": {"type": ["string", "null"]},
                "previous_jobs": {"type": "array", "items": {"type": "string"}},
                "projects_developed": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": ["string", "null"]},
                "extraction_confidence": {"type": "number"},
                "review_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["extraction_confidence"],
        },
    },
}


def _lm_studio_chat(messages: list, json_mode: bool = False) -> str:
    """
    Send a chat completion request to LM Studio (OpenAI-compatible endpoint)
    and return the assistant's text response.

    `json_mode=True` adds a `response_format` constrained to JSON schema output.
    LM Studio only accepts 'json_schema' or 'text' — 'json_object' is rejected
    with a 400 error. The schema used depends on the calling context; for
    generic JSON mode (e.g. rerank) we use the rerank schema.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is required for LM Studio support. Install requirements.txt.") from exc
    from .config import LM_STUDIO_MODEL, LM_STUDIO_BASE_URL
    client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
    kwargs = {"model": LM_STUDIO_MODEL, "messages": messages, "temperature": 0.2}
    if json_mode:
        kwargs["response_format"] = _RERANK_JSON_SCHEMA
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Extraction model
# ---------------------------------------------------------------------------

_LM_STUDIO_EXTRACT_SCHEMA = """
Return a JSON object with exactly these keys:
  name: string or null
  emails: array of strings
  phones: array of strings
  linkedin_url: string or null
  seniority: one of "Intern", "Junior", "Mid", "Senior", "Lead", "Principal", "Staff", or null
  years_of_experience: integer or null
  study_degrees: array of strings (each "<level> <field>, <institution>")
  technologies_used: array of strings (skills, frameworks, languages)
  languages_spoken: array of strings (spoken languages, not programming)
  location: string or null
  previous_jobs: array of strings (each "<title> at <company>")
  projects_developed: array of strings
  summary: string or null (1-3 sentence summary)
  extraction_confidence: float between 0.0 and 1.0
  review_flags: array of strings (any concerns worth human review; empty if none)

Use [] for missing arrays and null for missing scalars. Preserve any
CANDIDATE_001 / EMAIL_001 / PHONE_001 / LINKEDIN_001 anonymization tokens
exactly as they appear — do not invent or modify them.
""".strip()


def _extract_via_lm_studio(source_text: str, anon) -> Tuple["CandidateExtraction", Dict[str, Any]]:
    """Run extraction through LM Studio. Mirrors the Gemini path's anonymization
    and rehydration so callers get an identical CandidateExtraction back.

    `source_text` is the original (non-anonymized) text used only to build `anon`
    at the call site; `anon.anonymized_text` is what actually gets sent to the LLM.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is required for LM Studio support. Install requirements.txt.") from exc
    from .config import LM_STUDIO_MODEL, LM_STUDIO_BASE_URL
    client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
    messages = [
        {"role": "system", "content": "You are a precise HR data extraction assistant. " + _LM_STUDIO_EXTRACT_SCHEMA},
        {"role": "user", "content": f"Extract candidate profile from the following text:\n\n{anon.anonymized_text}"},
    ]
    resp = client.chat.completions.create(
        model=LM_STUDIO_MODEL,
        messages=messages,
        temperature=0.2,
        response_format=_EXTRACTION_JSON_SCHEMA,
    )
    raw_json = resp.choices[0].message.content
    parsed_dict = json.loads(raw_json)

    for field in ("name", "linkedin_url", "location", "summary"):
        if isinstance(parsed_dict.get(field), str):
            parsed_dict[field] = rehydrate_text(
                parsed_dict[field], anon.mapping, allowed=set(anon.mapping.keys())
            )
    for list_field in ("emails", "phones"):
        if isinstance(parsed_dict.get(list_field), list):
            parsed_dict[list_field] = [
                rehydrate_text(v, anon.mapping, allowed=set(anon.mapping.keys()))
                if isinstance(v, str) else v
                for v in parsed_dict[list_field]
            ]

    extraction = CandidateExtraction(**parsed_dict)
    provenance = {
        "provider": "lm_studio",
        "model": LM_STUDIO_MODEL,
        "schema": "CandidateExtraction_v1",
        "anonymized": True,
    }
    return extraction, provenance


def get_extraction_model():
    _configure_genai()
    return genai.GenerativeModel(
        model_name=get_active_model(DEFAULT_EXTRACT_MODEL),
        system_instruction=(
            "You are a precise HR data extraction assistant. "
            "Extract information from the provided resume/profile text into the exact requested JSON schema. "
            "If information is missing, use null or empty lists as appropriate. "
            "Estimate extraction confidence based on how clear and well-formatted the source text is (0.0 to 1.0). "
            "The text you receive may contain anonymization tokens such as CANDIDATE_001, EMAIL_001, PHONE_001 — "
            "preserve these tokens exactly in your JSON output."
        )
    )


def extract_candidate_data(text: str) -> Tuple["CandidateExtraction", Dict[str, Any]]:
    """
    Extract structured candidate data from raw text.

    When ENABLE_EXTERNAL_LLM is True: anonymises PII, sends to Gemini, then
    rehydrates real values back into the returned extraction.
    When False: falls back to the local heuristic extractor.

    Returns the parsed CandidateExtraction object and model provenance info.
    Raises ValueError if extraction fails or validation fails.
    """
    if not ENABLE_EXTERNAL_LLM:
        return extract_candidate_data_heuristic(text)

    use_local = get_use_local_llm()
    if not use_local and not (GEMINI_API_KEY or get_active_api_key()):
        return extract_candidate_data_heuristic(text)

    # --- Anonymise before sending to external LLM ---
    anon = anonymize_candidate_text(text)

    # Local LM Studio path — bypass Gemini entirely.
    if use_local:
        if not _lm_studio_available():
            # Local route requested but server is down — degrade gracefully.
            return extract_candidate_data_heuristic(text)
        return _extract_via_lm_studio(text, anon)

    model = get_extraction_model()

    try:
        response = model.generate_content(
            f"Extract candidate profile from the following text:\n\n{anon.anonymized_text}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CandidateExtraction
            )
        )

        raw_json = response.text
        parsed_dict = json.loads(raw_json)

        # Rehydrate PII tokens back into the structured fields
        for field in ("name", "linkedin_url", "location", "summary"):
            if isinstance(parsed_dict.get(field), str):
                parsed_dict[field] = rehydrate_text(
                    parsed_dict[field], anon.mapping, allowed=set(anon.mapping.keys())
                )
        for list_field in ("emails", "phones"):
            if isinstance(parsed_dict.get(list_field), list):
                parsed_dict[list_field] = [
                    rehydrate_text(v, anon.mapping, allowed=set(anon.mapping.keys()))
                    if isinstance(v, str) else v
                    for v in parsed_dict[list_field]
                ]

        extraction = CandidateExtraction(**parsed_dict)

        provenance_model_info = {
            "provider": "google",
            "model": get_active_model(DEFAULT_EXTRACT_MODEL),
            "schema": "CandidateExtraction_v1",
            "anonymized": True,
        }

        return extraction, provenance_model_info

    except json.JSONDecodeError as e:
        _quarantine_failed_output(text, getattr(response, "text", ""), "json_decode_error")
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")
    except ValidationError as e:
        _quarantine_failed_output(text, getattr(response, "text", ""), "schema_validation_error")
        raise ValueError(f"Extracted JSON did not match required schema: {str(e)}")
    except Exception as e:
        # Transient API failures (quota, network, server errors) shouldn't kill
        # the ingest — degrade to the heuristic extractor so the candidate is
        # still imported, just with lower-confidence fields.
        msg = str(e)
        if any(s in msg for s in ("429", "quota", "503", "504", "RESOURCE_EXHAUSTED", "timeout", "deadline")):
            return extract_candidate_data_heuristic(text)
        raise ValueError(f"Extraction failed: {msg}")


# ---------------------------------------------------------------------------
# Heuristic (local / offline) extractor
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}")
_LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w-]+/?")
_YOE_RE = re.compile(r"(\d+)\+?\s+years? of experience", re.IGNORECASE)
_TECH_KEYWORDS = [
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "C#", "Ruby", "PHP",
    "React", "Vue", "Angular", "Node.js", "FastAPI", "Django", "Flask", "Spring",
    "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
    "PyTorch", "TensorFlow", "scikit-learn", "Machine Learning", "NLP", "LLMs",
]
_LANG_KEYWORDS = [
    "English", "Romanian", "French", "German", "Spanish", "Italian",
    "Portuguese", "Dutch", "Polish", "Hungarian", "Czech",
]
_SENIORITY_RE = re.compile(
    r"\b(Junior|Mid-?level|Senior|Lead|Principal|Staff|Director|VP|Head of)\b",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"\b(Bachelor(?:'s)?|Master(?:'s)?|PhD|Ph\.D\.?|MBA|BSc|MSc|BEng|MEng)\b",
    re.IGNORECASE,
)


def extract_candidate_data_heuristic(text: str) -> Tuple["CandidateExtraction", Dict[str, Any]]:
    """
    Pure-local regex/keyword extraction — no external API calls.
    Used when ENABLE_EXTERNAL_LLM is False or GEMINI_API_KEY is absent.
    """
    emails = _EMAIL_RE.findall(text)
    phones = _PHONE_RE.findall(text)
    linkedin_url = next(iter(_LINKEDIN_RE.findall(text)), None)

    yoe_m = _YOE_RE.search(text)
    years_of_experience = int(yoe_m.group(1)) if yoe_m else None

    seniority_m = _SENIORITY_RE.search(text)
    seniority = seniority_m.group(1).capitalize() if seniority_m else None

    technologies_used = [kw for kw in _TECH_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)]
    languages_spoken = [lang for lang in _LANG_KEYWORDS if re.search(r"\b" + re.escape(lang) + r"\b", text, re.IGNORECASE)]
    study_degrees = list(dict.fromkeys(_DEGREE_RE.findall(text)))

    # Best-effort name: first non-empty line that looks like a person's name
    name = None
    for line in text.splitlines():
        line = line.strip()
        if line and not _EMAIL_RE.search(line) and not _PHONE_RE.search(line) and not _LINKEDIN_RE.search(line):
            parts = line.split()
            if 1 < len(parts) <= 5 and all(p[0].isupper() for p in parts if p):
                name = line
                break

    # Confidence: rough heuristic based on fields found
    filled = sum([
        bool(name), bool(emails), bool(years_of_experience),
        bool(technologies_used), bool(seniority),
    ])
    confidence = round(min(0.5 + filled * 0.08, 0.85), 2)

    extraction = CandidateExtraction(
        name=name,
        emails=emails,
        phones=phones,
        linkedin_url=linkedin_url,
        seniority=seniority,
        years_of_experience=years_of_experience,
        study_degrees=study_degrees,
        technologies_used=technologies_used,
        languages_spoken=languages_spoken,
        location=None,
        previous_jobs=[],
        projects_developed=[],
        summary=None,
        extraction_confidence=confidence,
        review_flags=["heuristic_extraction"],
    )

    return extraction, {"provider": "local", "model": "heuristic_v1", "anonymized": False}


# ---------------------------------------------------------------------------
# Quarantine helpers
# ---------------------------------------------------------------------------

def _quarantine_failed_output(source_text: str, raw_output: str, error_type: str):
    """Save failed extractions to quarantine for inspection."""
    quarantine_id = f"fail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if error_type in ("schema_validation_error", "json_decode_error"):
        folder = QUARANTINE_DIR / "schema_failures"
    else:
        folder = QUARANTINE_DIR / "parse_failures"

    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{quarantine_id}.json"

    quarantine_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "error_type": error_type,
        "model": get_active_model(DEFAULT_EXTRACT_MODEL),
        "source_text_snippet": anonymize_candidate_text(
            source_text[:1000] + "..." if len(source_text) > 1000 else source_text
        ).anonymized_text,
        "raw_output": anonymize_candidate_text(raw_output).anonymized_text,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quarantine_data, f, indent=2)
