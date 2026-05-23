import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import google.generativeai as genai

from .config import RECORDS_DIR, REQUIREMENTS_DIR, GEMINI_API_KEY
from .schemas import CandidateRecord, RequirementRecord
from .store import load_record
from .math_utils import get_embedding, cosine_similarity, calculate_keyword_overlap
from .security import anonymize_candidate_record, rehydrate_text
from .compliance import record_block_reasons

ENABLE_EXTERNAL_LLM = os.getenv("ENABLE_EXTERNAL_LLM", "true").lower() == "true"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-pro"


def get_rerank_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=(
            "You are an expert technical recruiter evaluating candidates against a job requirement. "
            "The candidate text you receive is anonymized — do not attempt to identify the person. "
            "Provide a JSON response evaluating why this candidate fits or doesn't fit."
        )
    )


def _load_requirement(req_id: str) -> RequirementRecord:
    # Guard against path traversal
    if "/" in req_id or "\\" in req_id or ".." in req_id:
        raise ValueError(f"Invalid requirement ID: {req_id!r}")
    path = (REQUIREMENTS_DIR / f"{req_id}.json").resolve()
    if not path.is_relative_to(REQUIREMENTS_DIR.resolve()):
        raise ValueError(f"Path traversal attempt detected for requirement ID: {req_id!r}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return RequirementRecord(**data)


def _get_all_active_candidates() -> List[str]:
    candidates = []
    if RECORDS_DIR.exists():
        for f in RECORDS_DIR.glob("*.json"):
            candidates.append(f.stem)
    return candidates


def filter_candidates(candidates: List[str], req: RequirementRecord) -> List[str]:
    """Stage 1: Compliance + location filter.

    Uses record_block_reasons() to enforce consent, retention, and other
    compliance flags — not just archived status — so non-consented candidates
    are never surfaced in shortlists.
    """
    passed = []
    req_location = req.requirements.location.lower() if req.requirements.location else None

    for c_id in candidates:
        rec = load_record(c_id)
        # Full compliance gate: archived, missing consent, retention expired, etc.
        if not rec or record_block_reasons(rec, c_id):
            continue
        if req_location and rec.profile.location:
            if req_location not in rec.profile.location.lower():
                continue
        passed.append(c_id)
    return passed


def score_keywords(candidates: List[str], req: RequirementRecord) -> Dict[str, float]:
    """Stage 2: Keyword overlap."""
    req_text = " ".join(req.requirements.must_have + req.requirements.nice_to_have)
    scores = {}
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec:
            continue
        cand_text = " ".join(rec.profile.technologies_used + [rec.profile.summary or ""])
        scores[c_id] = calculate_keyword_overlap(req_text, cand_text)
    return scores


def score_embeddings(candidates: List[str], req: RequirementRecord) -> Dict[str, float]:
    """Stage 3: Embedding similarity."""
    req_text = f"{req.title}. {req.description or ''} Requirements: " + " ".join(req.requirements.must_have)
    req_emb = get_embedding(req_text)

    scores = {}
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec:
            continue
        cand_text = (
            f"{rec.profile.headline or ''}. {rec.profile.summary or ''} "
            "Skills: " + " ".join(rec.profile.technologies_used)
        )
        cand_emb = get_embedding(cand_text)
        scores[c_id] = cosine_similarity(req_emb, cand_emb)

    return scores


def score_structured(candidates: List[str], req: RequirementRecord) -> Dict[str, Dict[str, float]]:
    """
    Stage 3b: Structured dimension scores (experience, location, language, freshness).
    Returns a per-candidate dict of dimension -> score (0.0-1.0).
    """
    from datetime import timezone, timedelta

    req_location = (req.requirements.location or "").lower()
    req_languages = {lang.lower() for lang in (req.requirements.language or [])}

    scores: Dict[str, Dict[str, float]] = {}
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec:
            continue

        # Experience: present = 1.0, missing = 0.5 (unknown)
        exp_score = 1.0 if rec.profile.years_of_experience is not None else 0.5

        # Location match
        loc_score = 1.0
        if req_location and rec.profile.location:
            loc_score = 1.0 if req_location in rec.profile.location.lower() else 0.0

        # Language match
        lang_score = 1.0
        if req_languages:
            cand_langs = {lang.lower() for lang in (rec.profile.languages_spoken or [])}
            lang_score = 1.0 if req_languages & cand_langs else 0.0

        # Freshness: penalise stale records
        freshness = 1.0
        if rec.state.stale:
            freshness = 0.5

        scores[c_id] = {
            "experience": exp_score,
            "location": loc_score,
            "language": lang_score,
            "freshness": freshness,
        }
    return scores


def generate_shortlist(req_id: str, top_n: int = 5, use_llm_rerank: bool = True) -> Dict[str, Any]:
    """Full matching pipeline: filter -> keywords -> embeddings -> structured -> optional LLM rerank."""
    req = _load_requirement(req_id)
    all_candidates = _get_all_active_candidates()

    # Stage 1: Filter
    filtered = filter_candidates(all_candidates, req)
    if not filtered:
        return {"job_id": req_id, "shortlist": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    # Stage 2: Keywords
    kw_scores = score_keywords(filtered, req)

    # Stage 3a: Embeddings
    emb_scores = score_embeddings(filtered, req)

    # Stage 3b: Structured dimensions
    struct_scores = score_structured(filtered, req)

    # Combine scores
    combined = []
    for c_id in filtered:
        s_kw = kw_scores.get(c_id, 0.0)
        s_emb = emb_scores.get(c_id, 0.0)
        s_struct = struct_scores.get(c_id, {})
        freshness = s_struct.get("freshness", 1.0)
        final_score = ((s_kw * 0.3) + (s_emb * 0.7)) * freshness
        combined.append((c_id, final_score))

    combined.sort(key=lambda x: x[1], reverse=True)
    top_candidates = combined[:top_n]

    shortlist = []

    for c_id, base_score in top_candidates:
        rec = load_record(c_id)
        if not rec:
            continue

        evidence = []
        uncertainty_flags = []
        review_required = False
        final_score = base_score

        if use_llm_rerank and ENABLE_EXTERNAL_LLM and GEMINI_API_KEY:
            # Anonymize before sending to external LLM
            anon = anonymize_candidate_record(rec, c_id)
            model = get_rerank_model()
            prompt = (
                f"Evaluate this candidate for this job.\n"
                f"Job: {req.title}\n"
                f"Requirements: {req.requirements.must_have}\n\n"
                f"Candidate (anonymized):\n{anon.anonymized_text}\n\n"
                "Return JSON with keys: 'match_score' (0.0 to 1.0), "
                "'evidence' (list of strings), 'uncertainty_flags' (list of strings)."
            )
            try:
                resp = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(response_mime_type="application/json")
                )
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
        else:
            evidence = ["Local similarity match"]

        shortlist.append({
            "record_id": c_id,
            "candidate_name": rec.identity.primary_name,
            "match_score": final_score,
            "evidence": evidence,
            "uncertainty_flags": uncertainty_flags,
            "review_required": review_required,
        })

    shortlist.sort(key=lambda x: x["match_score"], reverse=True)

    return {
        "job_id": req_id,
        "shortlist": shortlist,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
