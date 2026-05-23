import uuid
from datetime import datetime
import google.generativeai as genai

from .config import GEMINI_API_KEY
from .store import load_record
from .match import _load_requirement
from .review import add_to_queue

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-flash"

def get_draft_model():
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
        
    job = _load_requirement(job_id)
    
    prompt = (
        f"Write an outreach email to {candidate.identity.primary_name or 'the candidate'}.\n\n"
        f"Job Title: {job.title}\n"
        f"Job Requirements: {', '.join(job.requirements.must_have)}\n\n"
        f"Candidate Background:\n"
        f"- Headline: {candidate.profile.headline}\n"
        f"- Summary: {candidate.profile.summary}\n"
        f"- Skills: {', '.join(candidate.profile.technologies_used)}\n"
        f"- Experience: {candidate.profile.years_of_experience} years\n\n"
        f"Draft the email now:"
    )
    
    model = get_draft_model()
    response = model.generate_content(prompt)
    draft_text = response.text
    
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
        "model_used": MODEL_NAME
    }
    
    add_to_queue([case])
    return case_id
