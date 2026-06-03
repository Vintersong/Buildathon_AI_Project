import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import (
    REQUIREMENTS_DIR,
    ENABLE_EXTERNAL_OUTREACH_LLM,
    LOGS_DIR,
    get_active_provider,
)
from .schemas import CandidateRecord
from .store import load_record, save_record

OUTREACH_LOG_PATH = LOGS_DIR / "outreach_log.jsonl"


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

    from . import llm
    llm_available = ENABLE_EXTERNAL_OUTREACH_LLM and llm.llm_available()

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
            email_body = llm.complete([{"role": "user", "content": prompt}], json_mode=False)
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


# ---------------------------------------------------------------------------
# Review-queue outreach draft (used by POST /api/review/outreach-draft)
# ---------------------------------------------------------------------------

def _load_job(job_id: str) -> dict:
    """Load a requirement record as a raw dict."""
    path = REQUIREMENTS_DIR / f"{job_id}.json"
    if not path.exists():
        raise ValueError(f"Job {job_id} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _template_draft(record: CandidateRecord, job_title: str, must_have: List[str]) -> str:
    name = record.identity.primary_name or "there"
    first_name = name.split()[0] if name else "there"
    matched = [s for s in must_have if s in (record.profile.technologies_used or [])]
    skill_sentence = (
        f" Your experience with {', '.join(matched)} stood out in particular." if matched else ""
    )
    return (
        f"Hi {first_name},\n\n"
        f"I came across your profile while sourcing for a {job_title} role and was really "
        f"impressed by your background.{skill_sentence}\n\n"
        f"Would you be open to a short call to explore whether this could be a good fit?\n\n"
        f"Best regards,\nThe Talent Team"
    )


def generate_draft(candidate_id: str, job_id: str) -> str:
    """Generate a personalised outreach email and enqueue it for human review.

    Returns the created review case_id. Routes through the active LLM provider
    with PII anonymisation, falling back to a template when no provider is set.
    """
    from .compliance import record_block_reasons
    from .review import append_review_case
    from .security import anonymize_candidate_record, rehydrate_text
    from . import llm

    candidate = load_record(candidate_id)
    if not candidate:
        raise ValueError(f"Candidate {candidate_id} not found.")
    block_reasons = record_block_reasons(candidate)
    if block_reasons:
        raise ValueError(
            f"Candidate {candidate_id} is blocked for outreach: {', '.join(block_reasons)}"
        )

    job = _load_job(job_id)
    job_title = job.get("title", "the role")
    must_have = (job.get("requirements") or {}).get("must_have") or []

    generation_mode = "template"
    draft_text: Optional[str] = None

    if ENABLE_EXTERNAL_OUTREACH_LLM and llm.llm_available():
        try:
            anon = anonymize_candidate_record(candidate, candidate_id)
            prompt = (
                "Write an outreach email to CANDIDATE_001. "
                "The candidate profile is anonymized; do not ask for or include contact details.\n\n"
                f"Job Title: {job_title}\n"
                f"Job Requirements: {', '.join(must_have)}\n\n"
                f"Candidate Background:\n{anon.anonymized_text}\n\n"
                "Draft the email now:"
            )
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert technical recruiter writing a concise, personalized outreach email.",
                },
                {"role": "user", "content": prompt},
            ]
            raw = llm.complete(messages, json_mode=False)
            draft_text = rehydrate_text(raw, anon.mapping, allowed={"CANDIDATE"})
            generation_mode = get_active_provider()
        except Exception as e:
            print(f"[outreach] LLM draft failed for {candidate_id}: {e}")
            draft_text = None

    if draft_text is None:
        draft_text = _template_draft(candidate, job_title, must_have)

    case_id = f"review_{uuid.uuid4().hex[:12]}"
    case = {
        "case_id": case_id,
        "record_id": candidate_id,
        "job_id": job_id,
        "reason": "outreach_draft_review",
        "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        "status": "open",
        "draft_text": draft_text,
        "model_used": llm.active_model() if generation_mode != "template" else "local_template_v1",
        "generation_mode": generation_mode,
    }
    append_review_case(case)
    return case_id


def _log_outreach(record_id: str, job_title: str, company_name: str, method: str) -> None:
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
