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

# Number of candidates passed from embedding stage into LLM rerank.
# Wider funnel = better semantic recall, more LLM calls.
# Override via RERANK_FUNNEL_SIZE env var or the app config.
DEFAULT_RERANK_FUNNEL_SIZE = int(os.getenv("RERANK_FUNNEL_SIZE", "15"))

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-pro"


def get_rerank_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=(
            "You are an expert technical recruiter evaluating candidates against a job requirement. "
            "The candidate text you receive is anonymized — do not attempt to identify the person. "
            "Provide a JSON response evaluating why this candidate fits or doesn't fit. "
            "Consider semantic skill equivalence: e.g. Python experience is transferable to GDScript, "
            "Kotlin is transferable to Java, TypeScript subsumes JavaScript, etc."
        )
    )


def _load_requirement(req_id: str) -> RequirementRecord:
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
    compliance flags so non-consented candidates are never surfaced.
    Location filtering is soft: skipped if either side has no location data.
    """
    passed = []
    req_location = req.requirements.location.lower() if req.requirements.location else None

    for c_id in candidates:
        rec = load_record(c_id)
        if not rec or record_block_reasons(rec, c_id):
            continue
        if req_location and rec.profile.location:
            if req_location not in rec.profile.location.lower():
                continue
        passed.append(c_id)
    return passed


def score_embeddings(candidates: List[str], req: RequirementRecord) -> Dict[str, float]:
    """
    Stage 2: Semantic embedding similarity.

    Replaces keyword overlap as the primary ranking signal. Embeddings capture
    semantic equivalence (Python ↔ GDScript, Kotlin ↔ Java, etc.) that exact
    keyword matching misses entirely.
    """
    req_text = (
        f"{req.title}. {req.description or ''} "
        "Requirements: " + " ".join(req.requirements.must_have + req.requirements.nice_to_have)
    )
    req_emb = get_embedding(req_text)

    scores = {}
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec:
            continue
        cand_text = (
            f"{rec.profile.headline or ''}. {rec.profile.summary or ''} "
            "Skills: " + " ".join(rec.profile.technologies_used) +
            " Jobs: " + " ".join(rec.profile.previous_jobs or [])
        )
        cand_emb = get_embedding(cand_text)
        scores[c_id] = cosine_similarity(req_emb, cand_emb)

    return scores


def score_structured(candidates: List[str], req: RequirementRecord) -> Dict[str, Dict[str, float]]:
    """
    Stage 3: Structured dimension scores (experience, location, language, freshness).
    Used as a multiplier on top of embedding score, not as a gate.
    """
    req_location = (req.requirements.location or "").lower()
    req_languages = {lang.lower() for lang in (req.requirements.language or [])}

    scores: Dict[str, Dict[str, float]] = {}
    for c_id in candidates:
        rec = load_record(c_id)
        if not rec:
            continue

        exp_score = 1.0 if rec.profile.years_of_experience is not None else 0.5

        loc_score = 1.0
        if req_location and rec.profile.location:
            loc_score = 1.0 if req_location in rec.profile.location.lower() else 0.0

        lang_score = 1.0
        if req_languages:
            cand_langs = {lang.lower() for lang in (rec.profile.languages_spoken or [])}
            lang_score = 1.0 if req_languages & cand_langs else 0.0

        # Bug fix: guard against missing state field on older records
        state = getattr(rec, "state", None)
        freshness = 0.5 if (state and getattr(state, "stale", False)) else 1.0

        scores[c_id] = {
            "experience": exp_score,
            "location": loc_score,
            "language": lang_score,
            "freshness": freshness,
        }
    return scores


def persist_shortlist(req_id: str, shortlist: list, meta: dict) -> None:
    """Write shortlist results back into the requirement JSON for persistence across reloads."""
    path = (REQUIREMENTS_DIR / f"{req_id}.json").resolve()
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["shortlist"] = shortlist
        data["shortlist_meta"] = meta
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)
    except Exception as e:
        print(f"[match] Failed to persist shortlist for {req_id}: {e}")


def generate_shortlist(
    req_id: str,
    top_n: int = 5,
    funnel_size: int = DEFAULT_RERANK_FUNNEL_SIZE,
    use_llm_rerank: bool = True,
) -> Dict[str, Any]:
    """
    Full matching pipeline:
      Stage 1 — Compliance + location filter (hard gate)
      Stage 2 — Embedding similarity (semantic ranking, no keyword gate)
      Stage 3 — Structured dimension multipliers (freshness, language, etc.)
      Stage 4 — LLM rerank on top `funnel_size` candidates (deep contextual reasoning)
      → Return top `top_n` final results

    Keywords are retained as evidence metadata shown to the recruiter
    but are NOT used as a ranking signal, so semantically equivalent
    skills (Python ↔ GDScript, etc.) are never penalised.

    Results are persisted back to the requirement JSON so GET /api/jobs
    can return a populated shortlist without re-running the pipeline.
    """
    req = _load_requirement(req_id)
    all_candidates = _get_all_active_candidates()

    # Stage 1: Compliance + location filter
    filtered = filter_candidates(all_candidates, req)
    if not filtered:
        return {"job_id": req_id, "shortlist": [], "generated_at": datetime.utcnow().isoformat() + "Z"}

    # Stage 2: Embedding similarity
    emb_scores = score_embeddings(filtered, req)

    # Stage 3: Structured dimension multipliers
    struct_scores = score_structured(filtered, req)

    # Combine: embedding score * freshness multiplier
    combined = []
    for c_id in filtered:
        s_emb = emb_scores.get(c_id, 0.0)
        s_struct = struct_scores.get(c_id, {})
        freshness = s_struct.get("freshness", 1.0)
        final_score = s_emb * freshness
        combined.append((c_id, final_score))

    combined.sort(key=lambda x: x[1], reverse=True)

    # Keyword overlap computed for evidence metadata only — not for ranking
    req_skills = set(s.lower() for s in req.requirements.must_have + req.requirements.nice_to_have)

    def _keyword_evidence(rec: CandidateRecord) -> list[str]:
        cand_skills = set(s.lower() for s in rec.profile.technologies_used)
        exact = req_skills & cand_skills
        return [f"Exact skill match: {s}" for s in sorted(exact)]

    # Stage 4: LLM rerank on the wider funnel
    funnel = combined[:funnel_size]
    shortlist = []

    for c_id, base_score in funnel:
        rec = load_record(c_id)
        if not rec:
            continue

        evidence = []
        uncertainty_flags = []
        review_required = False
        final_score = base_score

        if use_llm_rerank and ENABLE_EXTERNAL_LLM and GEMINI_API_KEY:
            anon = anonymize_candidate_record(rec, c_id)
            model = get_rerank_model()
            prompt = (
                f"Evaluate this candidate for this job.\n"
                f"Job: {req.title}\n"
                f"Must-have skills: {req.requirements.must_have}\n"
                f"Nice-to-have skills: {req.requirements.nice_to_have}\n\n"
                f"Candidate (anonymized):\n{anon.anonymized_text}\n\n"
                "Consider semantic equivalences between skills where applicable.\n"
                "Return JSON with keys: 'match_score' (0.0 to 1.0), "
                "'evidence' (list of strings explaining the match), "
                "'uncertainty_flags' (list of strings for anything uncertain)."
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
                evidence = _keyword_evidence(rec) or ["Semantic similarity match (embedding)"]
        else:
            evidence = _keyword_evidence(rec) or ["Semantic similarity match (embedding)"]

        shortlist.append({
            "record_id": c_id,
            "candidate_name": rec.identity.primary_name,
            "match_score": round(final_score, 4),
            "evidence": evidence,
            "uncertainty_flags": uncertainty_flags,
            "review_required": review_required,
        })

    shortlist.sort(key=lambda x: x["match_score"], reverse=True)
    final_shortlist = shortlist[:top_n]

    meta = {
        "funnel_size": len(funnel),
        "total_filtered": len(filtered),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Persist results so GET /api/jobs returns populated shortlist after reload
    persist_shortlist(req_id, final_shortlist, meta)

    return {
        "job_id": req_id,
        "shortlist": final_shortlist,
        **meta,
    }
