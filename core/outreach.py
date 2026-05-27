import uuid
from datetime import datetime, timezone
from typing import Dict

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from .config import (
    get_active_api_key,
    get_active_model,
    get_use_local_llm,
    LM_STUDIO_BASE_URL,
    LM_STUDIO_MODEL,
    ENABLE_EXTERNAL_OUTREACH_LLM,
    LOGS_DIR,
)
from .schemas import CandidateRecord
from .store import load_record, save_record

OUTREACH_LOG_PATH = LOGS_DIR / "outreach_log.jsonl"
DEFAULT_OUTREACH_MODEL = "gemini-2.5-flash"


def _configure_genai() -> bool:
    key = get_active_api_key()
    if not key or genai is None:
        return False
    genai.configure(api_key=key)
    return True


def _template_email(record: CandidateRecord, job_title: str, company_name: str) -> str:
    name = record.identity.primary_name or "Candidate"
    first_name = name.split()[0] if name else "there"
    headline = record.profile.headline or "your background"
    skills_preview = ", ".join((record.profile.technologies_used or [])[:4]) or "your skills"
    return (
        f"Subject: Exciting {job_title} opportunity at {company_name}\n\n"
        f"Hi {first_name},\n\n"
        f"I came across your profile and was impressed by {headline}. "
        f"We have an opening for a {job_title} role at {company_name} that aligns well with "
        f"your experience in {skills_preview}.\n\n"
        f"Would you be open to a brief conversation to explore this further?\n\n"
        f"Best regards,\n{company_name} Talent Team"
    )


def draft_outreach_email(
    record_id: str,
    job_title: str,
    company_name: str = "our company",
) -> Dict:
    record = load_record(record_id)
    use_local = get_use_local_llm()
    llm_available = use_local or (ENABLE_EXTERNAL_OUTREACH_LLM and _configure_genai())

    if not llm_available:
        email_body = _template_email(record, job_title, company_name)
        method = "template"
    else:
        try:
            name = record.identity.primary_name or "the candidate"
            headline = record.profile.headline or ""
            skills = ", ".join((record.profile.technologies_used or [])[:8])
            prompt = (
                f"Write a concise, warm outreach email to recruit {name} for a {job_title} role "
                f"at {company_name}. Candidate background: {headline}. Key skills: {skills}. "
                f"Keep it under 150 words. No subject line. Start with 'Hi [first name],'."
            )

            if use_local:
                from .extract import _lm_studio_chat
                email_body = _lm_studio_chat(
                    [{"role": "user", "content": prompt}],
                    json_mode=False,
                )
            else:
                model = genai.GenerativeModel(model_name=get_active_model(DEFAULT_OUTREACH_MODEL))
                response = model.generate_content(prompt)
                email_body = response.text
            method = "llm"
        except Exception as e:
            print(f"[outreach] LLM failed: {e}; falling back to template")
            email_body = _template_email(record, job_title, company_name)
            method = "template_fallback"

    event = {
        "event": "outreach_drafted",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "job_title": job_title,
        "company_name": company_name,
        "method": method,
    }
    save_record(record_id, record, event=event)

    _log_outreach(record_id, job_title, company_name, method)
    return {"record_id": record_id, "email_draft": email_body, "method": method}


def _log_outreach(record_id: str, job_title: str, company_name: str, method: str) -> None:
    import json
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "record_id": record_id,
        "job_title": job_title,
        "company_name": company_name,
        "method": method,
    }
    with open(OUTREACH_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
