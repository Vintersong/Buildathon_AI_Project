import json
import logging
import re
import warnings
from typing import Dict, Any, Tuple
from pydantic import ValidationError
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from .config import QUARANTINE_DIR, ENABLE_EXTERNAL_LLM, ENABLE_LOCAL_LLM, LM_STUDIO_URL, LM_STUDIO_MODEL
from .schemas import CandidateExtraction
from .security import anonymize_candidate_text, redact_pii

def _configure_genai() -> bool:
    """Read env vars at call time so dotenv loading order doesn't matter."""
    import os
    enable = os.getenv("ENABLE_EXTERNAL_LLM", "").strip().lower() in {"1", "true", "yes", "on"}
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not enable:
        return False
    if genai and key:
        genai.configure(api_key=key)
        return True
    warnings.warn("GEMINI_API_KEY not found in environment — LLM extraction disabled.")
    return False

MODEL_NAME = "gemini-3.5-flash"


# ---------------------------------------------------------------------------
# LM Studio (local, OpenAI-compatible)
# ---------------------------------------------------------------------------

def _lm_studio_available() -> bool:
    if not ENABLE_LOCAL_LLM:
        return False
    import urllib.request
    try:
        urllib.request.urlopen(f"{LM_STUDIO_URL}/models", timeout=2)
        return True
    except Exception:
        return False


def _lm_studio_chat(messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
    """Call LM Studio's OpenAI-compatible /chat/completions endpoint."""
    import urllib.request as _req
    import urllib.error
    payload = json.dumps({
        "model": LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    request = _req.Request(
        f"{LM_STUDIO_URL}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _req.urlopen(request, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


_LM_EXTRACT_SYSTEM = (
    "You are a precise HR data extraction assistant. "
    "Extract candidate information from resume text and return ONLY valid JSON — no markdown, no explanation. "
    "Use null for missing fields. Confidence is 0.0–1.0."
)

_LM_EXTRACT_SCHEMA = """{
  "name": "string or null",
  "seniority": "Senior|Mid|Junior|Lead|Principal|Intern or null",
  "years_of_experience": "integer or null",
  "technologies_used": ["list of technology strings"],
  "languages_spoken": ["list of language strings"],
  "study_degrees": ["list of degree strings"],
  "location": "string or null",
  "previous_jobs": ["list of job title strings"],
  "summary": "one or two sentence summary or null",
  "extraction_confidence": "float 0.0-1.0"
}"""


def _extract_with_lm_studio(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """Use local LM Studio to enhance heuristic extraction."""
    local_extraction, local_model_info = extract_candidate_data_heuristic(text)

    prompt = (
        f"Extract candidate profile from the resume below.\n"
        f"Return ONLY JSON matching this schema:\n{_LM_EXTRACT_SCHEMA}\n\n"
        f"Resume:\n{text[:4000]}\n\nJSON:"
    )
    raw = _lm_studio_chat(
        [{"role": "system", "content": _LM_EXTRACT_SYSTEM}, {"role": "user", "content": prompt}]
    )

    # Strip markdown fences if model wraps the output
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())

    parsed = json.loads(raw)
    extraction = CandidateExtraction(
        name=local_extraction.name,
        emails=local_extraction.emails,
        phones=local_extraction.phones,
        linkedin_url=local_extraction.linkedin_url,
        seniority=parsed.get("seniority") or local_extraction.seniority,
        years_of_experience=parsed.get("years_of_experience") or local_extraction.years_of_experience,
        technologies_used=parsed.get("technologies_used") or local_extraction.technologies_used,
        languages_spoken=parsed.get("languages_spoken") or local_extraction.languages_spoken,
        study_degrees=parsed.get("study_degrees") or local_extraction.study_degrees,
        location=parsed.get("location") or local_extraction.location,
        previous_jobs=parsed.get("previous_jobs") or local_extraction.previous_jobs,
        projects_developed=local_extraction.projects_developed,
        summary=parsed.get("summary") or local_extraction.summary,
        extraction_confidence=float(parsed.get("extraction_confidence", 0.75)),
        review_flags=["lm_studio_extraction"],
    )
    provenance = {
        "provider": "lm_studio",
        "model": LM_STUDIO_MODEL,
        "schema": "CandidateExtraction_v1",
        "external": False,
        "url": LM_STUDIO_URL,
    }
    return extraction, provenance

TECHNOLOGIES = [
    "Python", "JavaScript", "TypeScript", "Java", "C#", "C++", "Go", "Rust",
    "React", "Angular", "Vue", "Node.js", "FastAPI", "Django", "Flask",
    "PyTorch", "TensorFlow", "Machine Learning", "LLMs", "NLP", "SQL",
    "PostgreSQL", "MySQL", "MongoDB", "Docker", "Kubernetes", "AWS", "Azure",
    "GCP", "Git", "Linux", "Spark", "Airflow"
]
LANGUAGES = ["English", "Romanian", "German", "French", "Spanish", "Italian"]
DEGREES = ["Bachelor", "Master", "PhD", "BSc", "MSc", "MBA"]
SENIORITY_PATTERNS = [
    ("lead", "Lead"),
    ("principal", "Principal"),
    ("senior", "Senior"),
    ("mid", "Mid"),
    ("junior", "Junior"),
    ("intern", "Intern"),
]

def get_extraction_model():
    if not genai:
        raise ValueError("google-generativeai is not installed")
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction="You are a precise HR data extraction assistant. Extract information from the provided resume/profile text into the exact requested JSON schema. If information is missing, use null or empty lists as appropriate. Estimate extraction confidence based on how clear and well-formatted the source text is (0.0 to 1.0)."
    )

def extract_candidate_data(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """
    Extract structured candidate data from raw text.
    Priority: LM Studio (local) → Gemini (external) → heuristic fallback.
    Never raises on transient API errors — always returns at minimum the heuristic result.
    """
    local_extraction, local_model_info = extract_candidate_data_heuristic(text)

    # 1. Try local LM Studio first (private, no quota limits)
    if _lm_studio_available():
        try:
            return _extract_with_lm_studio(text)
        except Exception as e:
            logger.warning("LM Studio extraction failed, trying next provider: %s", e)
            local_extraction.review_flags.append("lm_studio_fallback")

    # 2. Try Gemini if enabled
    if not ENABLE_EXTERNAL_LLM:
        return local_extraction, local_model_info
    if not _configure_genai():
        local_extraction.review_flags.append("external_llm_unavailable")
        return local_extraction, local_model_info

    model = get_extraction_model()
    response = None
    anonymized = anonymize_candidate_text(text, candidate_id="candidate")

    try:
        response = model.generate_content(
            "Extract candidate profile from the following anonymized text. "
            "Do not infer names, emails, phone numbers, LinkedIn URLs, or other direct identifiers; "
            "leave those fields null or empty if only placeholders are present.\n\n"
            f"{anonymized.anonymized_text}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CandidateExtraction
            )
        )

        raw_json = response.text
        parsed_dict = json.loads(raw_json)

        extraction = CandidateExtraction(**parsed_dict)
        extraction.name = local_extraction.name
        extraction.emails = local_extraction.emails
        extraction.phones = local_extraction.phones
        extraction.linkedin_url = local_extraction.linkedin_url
        extraction.review_flags = list(dict.fromkeys(extraction.review_flags + ["external_anonymized_extraction"]))

        return extraction, {
            "provider": "google",
            "model": MODEL_NAME,
            "schema": "CandidateExtraction_v1",
            "external": True,
            "anonymized": True,
            "redacted_types": anonymized.redacted_types,
        }

    except json.JSONDecodeError as e:
        _quarantine_failed_output(anonymized.anonymized_text, getattr(response, 'text', ''), "json_decode_error")
        logger.warning("Gemini JSON decode failed, falling back to heuristic: %s", e)
        local_extraction.review_flags.append("llm_json_error_fallback")
        return local_extraction, local_model_info

    except ValidationError as e:
        _quarantine_failed_output(anonymized.anonymized_text, getattr(response, 'text', ''), "schema_validation_error")
        logger.warning("Gemini schema validation failed, falling back to heuristic: %s", e)
        local_extraction.review_flags.append("llm_schema_error_fallback")
        return local_extraction, local_model_info

    except Exception as e:
        err_str = str(e)
        # Rate-limit / quota exhausted — degrade gracefully
        if any(k in err_str.lower() for k in ("429", "quota", "rate", "exhausted", "resource_exhausted")):
            logger.warning("Gemini quota/rate-limit hit, falling back to heuristic: %s", err_str[:200])
            local_extraction.review_flags.append("llm_quota_fallback")
            return local_extraction, local_model_info
        raise ValueError(f"Extraction failed: {err_str}")

def extract_candidate_data_heuristic(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """Deterministic offline extraction used by default to avoid data exfiltration."""
    normalized = text or ""
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    lower = normalized.lower()

    emails = _unique(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", normalized))
    phones = _unique(match.group(0).strip() for match in re.finditer(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", normalized))
    linkedin_matches = re.findall(r"https?://(?:[\w]+\.)?linkedin\.com/[^\s)>\"]+", normalized, flags=re.IGNORECASE)
    linkedin_url = linkedin_matches[0] if linkedin_matches else None

    name = _guess_name(lines)
    seniority = _guess_seniority(lower)
    years = _guess_years(lower)
    degrees = _find_terms(normalized, DEGREES)
    technologies = _find_terms(normalized, TECHNOLOGIES)
    languages = _find_terms(normalized, LANGUAGES)
    location = _guess_location(lines)
    previous_jobs = _guess_previous_jobs(lines)
    projects = _guess_projects(lines)
    summary = _guess_summary(lines)

    confidence = 0.35
    confidence += 0.1 if name else 0.0
    confidence += 0.1 if emails or linkedin_url else 0.0
    confidence += 0.1 if technologies else 0.0
    confidence += 0.05 if seniority else 0.0
    confidence += 0.05 if years is not None else 0.0
    confidence = min(confidence, 0.7)

    review_flags = ["heuristic_extraction"]
    if not emails and not linkedin_url:
        review_flags.append("missing_contact_signal")
    if confidence < 0.75:
        review_flags.append("low_extraction_confidence")

    extraction = CandidateExtraction(
        name=name,
        emails=emails,
        phones=phones,
        linkedin_url=linkedin_url,
        seniority=seniority,
        years_of_experience=years,
        study_degrees=degrees,
        technologies_used=technologies,
        languages_spoken=languages,
        location=location,
        previous_jobs=previous_jobs,
        projects_developed=projects,
        summary=summary,
        extraction_confidence=confidence,
        review_flags=review_flags,
    )
    return extraction, {
        "provider": "local",
        "model": "heuristic_extractor_v1",
        "schema": "CandidateExtraction_v1",
        "external": False,
    }

def _unique(values) -> list:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

def _guess_name(lines: list) -> str | None:
    for line in lines[:8]:
        if any(token in line.lower() for token in ["@", "linkedin", "github", "http", "curriculum", "resume", "cv"]):
            continue
        words = re.findall(r"[A-Z][a-zA-Z'-]+", line)
        if 2 <= len(words) <= 4 and len(line) <= 80:
            return " ".join(words)
    return None

def _guess_seniority(lower_text: str) -> str | None:
    for needle, label in SENIORITY_PATTERNS:
        if needle in lower_text:
            return label
    return None

def _guess_years(lower_text: str) -> int | None:
    patterns = [
        r"(\d{1,2})\+?\s*(?:years|yrs)\s+(?:of\s+)?experience",
        r"experience\s*[:\-]?\s*(\d{1,2})\+?\s*(?:years|yrs)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower_text)
        if match:
            return int(match.group(1))
    return None

def _find_terms(text: str, terms: list[str]) -> list[str]:
    found = []
    for term in terms:
        pattern = r"(?<![\w+#.-])" + re.escape(term) + r"(?![\w+#.-])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(term)
    return found

def _guess_location(lines: list) -> str | None:
    for line in lines:
        lower = line.lower()
        if "remote" in lower:
            return "Remote"
        if lower.startswith(("location:", "based in", "address:")):
            return re.sub(r"^(location:|based in|address:)\s*", "", line, flags=re.IGNORECASE).strip()
    return None

def _guess_previous_jobs(lines: list) -> list[str]:
    jobs = []
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in ["engineer", "developer", "manager", "consultant", "analyst", "scientist"]):
            if any(token in lower for token in [" at ", " - ", "|", "company", "present", "20"]):
                jobs.append(line[:160])
    return _unique(jobs[:8])

def _guess_projects(lines: list) -> list[str]:
    projects = []
    capture = False
    for line in lines:
        lower = line.lower()
        if "project" in lower:
            capture = True
            projects.append(line[:180])
            continue
        if capture and len(projects) < 5 and len(line) > 30:
            projects.append(line[:180])
    return _unique(projects[:5])

def _guess_summary(lines: list) -> str | None:
    candidates = [line for line in lines if 40 <= len(line) <= 240 and "@" not in line and "linkedin" not in line.lower()]
    if not candidates:
        return None
    return " ".join(candidates[:2])[:400]

def _quarantine_failed_output(source_text: str, raw_output: str, error_type: str):
    """Save failed extractions to quarantine for inspection."""
    quarantine_id = f"fail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # Decide subfolder based on error type
    if error_type == "schema_validation_error" or error_type == "json_decode_error":
        folder = QUARANTINE_DIR / "schema_failures"
    else:
        folder = QUARANTINE_DIR / "parse_failures"
    folder.mkdir(parents=True, exist_ok=True)
        
    file_path = folder / f"{quarantine_id}.json"
    
    quarantine_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "error_type": error_type,
        "model": MODEL_NAME,
        "source_text_snippet": redact_pii(source_text[:1000] + "..." if len(source_text) > 1000 else source_text),
        "raw_output": redact_pii(raw_output[:2000] + "..." if len(raw_output) > 2000 else raw_output)
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quarantine_data, f, indent=2)
