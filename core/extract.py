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

# We use gemini-1.5-flash for fast and cost-effective structured extraction
MODEL_NAME = "gemini-1.5-flash"

def get_extraction_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction="You are a precise HR data extraction assistant. Extract information from the provided resume/profile text into the exact requested JSON schema. If information is missing, use null or empty lists as appropriate. Estimate extraction confidence based on how clear and well-formatted the source text is (0.0 to 1.0)."
    )

def extract_candidate_data(text: str) -> Tuple[CandidateExtraction, Dict[str, Any]]:
    """
    Extract structured candidate data from raw text using Gemini.
    Returns the parsed CandidateExtraction object and model provenance info.
    Raises ValueError if extraction fails or validation fails.
    """
    model = get_extraction_model()
    
    try:
        # Request JSON output matching the CandidateExtraction schema
        response = model.generate_content(
            f"Extract candidate profile from the following text:\n\n{text}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CandidateExtraction
            )
        )
        
        raw_json = response.text
        parsed_dict = json.loads(raw_json)
        
        # Validate against schema
        extraction = CandidateExtraction(**parsed_dict)
        
        # Build provenance info
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
    
    # Decide subfolder based on error type
    if error_type == "schema_validation_error" or error_type == "json_decode_error":
        folder = QUARANTINE_DIR / "schema_failures"
    else:
        folder = QUARANTINE_DIR / "parse_failures"
        
    file_path = folder / f"{quarantine_id}.json"
    
    quarantine_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "error_type": error_type,
        "model": MODEL_NAME,
        "source_text_snippet": source_text[:1000] + "..." if len(source_text) > 1000 else source_text,
        "raw_output": raw_output
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quarantine_data, f, indent=2)
