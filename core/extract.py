import json
from typing import Dict, Any, Tuple
import google.generativeai as genai
from pydantic import ValidationError
from datetime import datetime
import uuid

from .config import GEMINI_API_KEY, QUARANTINE_DIR
from .schemas import CandidateExtraction

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
        model="local-model",  # LM Studio ignores this; uses whichever model is loaded
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
            "Estimate extraction confidence based on how clear and well-formatted the source text is (0.0 to 1.0)."
        )
    )


def extract_candidate_data(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """
    Extract structured candidate data from raw text using Gemini.
    Returns the parsed CandidateExtraction object and model provenance info.
    Raises ValueError if extraction fails or validation fails.
    """
    model = get_extraction_model()

    try:
        response = model.generate_content(
            f"Extract candidate profile from the following text:\n\n{text}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CandidateExtraction
            )
        )

        raw_json = response.text
        parsed_dict = json.loads(raw_json)
        extraction = CandidateExtraction(**parsed_dict)

        provenance_model_info = {
            "provider": "google",
            "model": MODEL_NAME,
            "schema": "CandidateExtraction_v1"
        }

        return extraction, provenance_model_info

    except json.JSONDecodeError as e:
        _quarantine_failed_output(text, getattr(response, 'text', ''), "json_decode_error")
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")
    except ValidationError as e:
        _quarantine_failed_output(text, getattr(response, 'text', ''), "schema_validation_error")
        raise ValueError(f"Extracted JSON did not match required schema: {str(e)}")
    except Exception as e:
        raise ValueError(f"Extraction failed: {str(e)}")


def _quarantine_failed_output(source_text: str, raw_output: str, error_type: str):
    """Save failed extractions to quarantine for inspection."""
    quarantine_id = f"fail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if error_type in ("schema_validation_error", "json_decode_error"):
        folder = QUARANTINE_DIR / "schema_failures"
    else:
        folder = QUARANTINE_DIR / "parse_failures"

    folder.mkdir(parents=True, exist_ok=True)  # ensure folder exists
    file_path = folder / f"{quarantine_id}.json"

    quarantine_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
tml        "error_type": error_type,
        "model": MODEL_NAME,
        "source_text_snippet": source_text[:1000] + "..." if len(source_text) > 1000 else source_text,
        "raw_output": raw_output
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quarantine_data, f, indent=2)
