import json
import re
from typing import Dict, Any, Tuple
import google.generativeai as genai
from pydantic import ValidationError
from datetime import datetime
import uuid

from .config import GEMINI_API_KEY, QUARANTINE_DIR
from .schemas import CandidateExtraction
from .security import anonymize_candidate_text, rehydrate_text

# Feature flag — when False the external LLM call is skipped and the
# heuristic fallback is used instead (safe for air-gapped / no-key deploys).
import os
ENABLE_EXTERNAL_LLM = os.getenv("ENABLE_EXTERNAL_LLM", "true").lower() == "true"

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY not found in environment.")

MODEL_NAME = "gemini-1.5-flash"


# ---------------------------------------------------------------------------
# LM Studio helpers (used by web/app.py chat endpoint)
# ---------------------------------------------------------------------------

def _configure_genai() -> bool:
    """Return True if Gemini is configured and an API key is available."""
    return bool(GEMINI_API_KEY)


def _lm_studio_available() -> bool:
    """Return True if a local LM Studio server is reachable on port 1234."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:1234/v1/models", timeout=1)
        return True
    except Exception:
        return False


def _lm_studio_chat(messages: list) -> str:
    """
    Send a chat completion request to LM Studio (OpenAI-compatible endpoint)
    and return the assistant's text response.
    """
    from openai import OpenAI
    client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
    resp = client.chat.completions.create(
        model="local-model",
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Extraction model
# ---------------------------------------------------------------------------

def get_extraction_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=(
            "You are a precise HR data extraction assistant. "
            "Extract information from the provided resume/profile text into the exact requested JSON schema. "
            "If information is missing, use null or empty lists as appropriate. "
            "Estimate extraction confidence based on how clear and well-formatted the source text is (0.0 to 1.0). "
            "The text you receive may contain anonymization tokens such as CANDIDATE_001, EMAIL_001, PHONE_001 — "
            "preserve these tokens exactly in your JSON output."
        )
    )


def extract_candidate_data(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """
    Extract structured candidate data from raw text.

    When ENABLE_EXTERNAL_LLM is True: anonymises PII, sends to Gemini, then
    rehydrates real values back into the returned extraction.
    When False: falls back to the local heuristic extractor.

    Returns the parsed CandidateExtraction object and model provenance info.
    Raises ValueError if extraction fails or validation fails.
    """
    if not ENABLE_EXTERNAL_LLM or not GEMINI_API_KEY:
        return extract_candidate_data_heuristic(text)

    # --- Anonymise before sending to external LLM ---
    anon = anonymize_candidate_text(text)
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
            "model": MODEL_NAME,
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
        raise ValueError(f"Extraction failed: {str(e)}")


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


def extract_candidate_data_heuristic(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
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
        "model": MODEL_NAME,
        "source_text_snippet": anonymize_candidate_text(
            source_text[:1000] + "..." if len(source_text) > 1000 else source_text
        ).anonymized_text,
        "raw_output": anonymize_candidate_text(raw_output).anonymized_text,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quarantine_data, f, indent=2)
