import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import google.generativeai as genai

from .config import RECORDS_DIR, REQUIREMENTS_DIR, GEMINI_API_KEY
from .schemas import CandidateRecord, RequirementRecord
from .store import load_record
from .math_utils import get_embedding, cosine_similarity, calculate_keyword_overlap

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-pro"  # Use Pro for deep reranking

def get_rerank_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction="You are an expert technical recruiter evaluating candidates against a job requirement. Provide a JSON response evaluating why this candidate fits or doesn't fit."
    )

def _load_requirement(req_id: str) -> RequirementRecord:
    path = REQUIREMENTS_DIR / f"{req_id}.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return RequirementRecord(**data)

def _get_all_active_candidates() -> List[str]:
    # In a real app we'd query the record_index.json, for now we list the dir
    candidates = []
    if RECORDS_DIR.exists():
        for f in RECORDS_DIR.glob("*.json"):
            candidates.append(f.stem)
    return candidates

def filter_candidates(candidates: List[str], req: RequirementRecord) -> List[str]:
    """Stage 1: Local structured filter (status, location, degree)"""
    passed = []
    req_location = req.requirements.location.lower() if req.requirements.location else None
    
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec or rec.state.status == "archived":
            continue
            
        # Optional: location check
        if req_location and rec.profile.location:
            if req_location not in rec.profile.location.lower():
                continue
                
        passed.append(c_id)
    return passed

def score_keywords(candidates: List[str], req: RequirementRecord) -> Dict[str, float]:
    """Stage 2: Keyword overlap"""
    req_text = " ".join(req.requirements.must_have + req.requirements.nice_to_have)
    scores = {}
    for c_id in candidates:
        rec = load_record(c_id)
        cand_text = " ".join(rec.profile.technologies_used + [rec.profile.summary or ""])
        scores[c_id] = calculate_keyword_overlap(req_text, cand_text)
    return scores

def score_embeddings(candidates: List[str], req: RequirementRecord) -> Dict[str, float]:
    """Stage 3: Embedding similarity"""
    req_text = f"{req.title}. {req.description or ''} Requirements: " + " ".join(req.requirements.must_have)
    req_emb = get_embedding(req_text)
    
    scores = {}
    for c_id in candidates:
        rec = load_record(c_id)
        cand_text = f"{rec.profile.headline or ''}. {rec.profile.summary or ''} Skills: " + " ".join(rec.profile.technologies_used)
        cand_emb = get_embedding(cand_text)
        scores[c_id] = cosine_similarity(req_emb, cand_emb)
        
    return scores

def generate_shortlist(req_id: str, top_n: int = 5, use_llm_rerank: bool = True) -> Dict[str, Any]:
    """Full 4-stage matching pipeline."""
    req = _load_requirement(req_id)
    all_candidates = _get_all_active_candidates()
    
    # Stage 1: Filter
    filtered = filter_candidates(all_candidates, req)
    if not filtered:
        return {"job_id": req_id, "shortlist": [], "generated_at": datetime.utcnow().isoformat()}
        
    # Stage 2: Keywords
    kw_scores = score_keywords(filtered, req)
    
    # Stage 3: Embeddings
    emb_scores = score_embeddings(filtered, req)
    
    # Combine scores (simple weighted average)
    combined = []
    for c_id in filtered:
        s_kw = kw_scores[c_id]
        s_emb = emb_scores[c_id]
        final_score = (s_kw * 0.3) + (s_emb * 0.7)
        combined.append((c_id, final_score))
        
    # Sort and take top N
    combined.sort(key=lambda x: x[1], reverse=True)
    top_candidates = combined[:top_n]
    
    shortlist = []
    
    # Stage 4: Optional LLM Rerank
    for c_id, base_score in top_candidates:
        rec = load_record(c_id)
        
        evidence = []
        review_required = False
        
        if use_llm_rerank:
            model = get_rerank_model()
            prompt = f"Evaluate this candidate for this job.\nJob: {req.title}\nRequirements: {req.requirements.must_have}\n\nCandidate: {rec.identity.primary_name}\nSummary: {rec.profile.summary}\nSkills: {rec.profile.technologies_used}\n\nReturn JSON with keys: 'match_score' (0.0 to 1.0), 'evidence' (list of strings), 'uncertainty_flags' (list of strings)."
            try:
                resp = model.generate_content(prompt, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
                eval_data = json.loads(resp.text)
                final_score = eval_data.get("match_score", base_score)
                evidence = eval_data.get("evidence", [])
                uncertainty_flags = eval_data.get("uncertainty_flags", [])
                if uncertainty_flags:
                    review_required = True
            except Exception as e:
                print(f"LLM rerank failed for {c_id}: {e}")
                final_score = base_score
                evidence = ["Local similarity match (fallback)"]
                uncertainty_flags = []
        else:
            final_score = base_score
            evidence = ["Local similarity match"]
            uncertainty_flags = []
            
        shortlist.append({
            "record_id": c_id,
            "candidate_name": rec.identity.primary_name,
            "match_score": final_score,
            "evidence": evidence,
            "uncertainty_flags": uncertainty_flags,
            "review_required": review_required
        })
        
    # Sort again by the final score
    shortlist.sort(key=lambda x: x["match_score"], reverse=True)
    
    return {
        "job_id": req_id,
        "shortlist": shortlist,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }
