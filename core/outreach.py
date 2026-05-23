import uuid
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from .config import GEMINI_API_KEY, ENABLE_EXTERNAL_OUTREACH_LLM
from .store import load_record
from .match import _load_requirement
from .review import add_to_queue
from .compliance import record_block_reasons
from .security import anonymize_candidate_record, rehydrate_text

if genai and GEMINI_API_KEY and ENABLE_EXTERNAL_OUTREACH_LLM:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.5-flash"

def get_draft_model():
    if not genai:
        raise ValueError("google-generativeai is not installed")
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction="You are an expert technical recruiter writing an outreach email. "
                           "The email should be professional, personalized, and highlight why the candidate's specific background is a great fit for the role. "
                           "Keep it concise. Do not use placeholders like [Your Name] unless absolutely necessary; leave signature generic."
    )

def generate_draft(candidate_id: str, job_id: str) -> str:
    """
    Generate a personalized outreach email and add it to the human-in-the-loop review queue.
    Returns the generated case_id.
    """
    candidate = load_record(candidate_id)
    if not candidate:
        raise ValueError(f"Candidate {candidate_id} not found.")
    block_reasons = record_block_reasons(candidate, candidate_id)
    if block_reasons:
        raise ValueError(f"Candidate {candidate_id} is blocked for outreach: {', '.join(block_reasons)}")
        
    job = _load_requirement(job_id)

    generation_mode = "template"
    if ENABLE_EXTERNAL_OUTREACH_LLM and GEMINI_API_KEY and genai:
        anonymized = anonymize_candidate_record(candidate, candidate_id)
        prompt = (
            "Write an outreach email to CANDIDATE_001. "
            "The candidate profile is anonymized; do not ask for or include contact details.\n\n"
            f"Job Title: {job.title}\n"
            f"Job Requirements: {', '.join(job.requirements.must_have)}\n\n"
            f"Candidate Background:\n{anonymized.anonymized_text}\n\n"
            f"Draft the email now:"
        )
        model = get_draft_model()
        response = model.generate_content(prompt)
        draft_text = rehydrate_text(response.text, anonymized.mapping, allowed={"CANDIDATE"})
        generation_mode = "external_llm"
    else:
        draft_text = _template_draft(candidate, job)
    
    # Create the review case
    case_id = f"review_{uuid.uuid4().hex[:12]}"
    case = {
        "case_id": case_id,
        "record_id": candidate_id,
        "job_id": job_id,
        "reason": "outreach_draft_review",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "open",
        "draft_text": draft_text,
        "model_used": MODEL_NAME if generation_mode == "external_llm" else "local_template_v1",
        "generation_mode": generation_mode
    }
    
    add_to_queue([case])
    return case_id

def _template_draft(candidate, job) -> str:
    name = candidate.identity.primary_name or "there"
    skills = [skill for skill in job.requirements.must_have if skill in candidate.profile.technologies_used]
    skill_sentence = ""
    if skills:
        skill_sentence = f" Your background with {', '.join(skills[:4])} stood out for this role."
    experience = ""
    if candidate.profile.years_of_experience is not None:
        experience = f" I also noticed your {candidate.profile.years_of_experience} years of experience."
    return (
        f"Hi {name},\n\n"
        f"We are reviewing candidates for the {job.title} opportunity.{skill_sentence}{experience}\n\n"
        "Would you be open to a short conversation to confirm whether this role matches your current interests?\n\n"
        "Best regards,\n"
        "Talent Team"
    )
