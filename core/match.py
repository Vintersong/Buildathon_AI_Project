import json
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import google.generativeai as genai

from .config import (
    GEMINI_API_KEY,
    RECORDS_DIR,
    REQUIREMENTS_DIR,
    get_active_api_key,
    get_active_model,
    get_use_local_llm,
    ENABLE_EXTERNAL_LLM,
)
from .schemas import CandidateRecord, RequirementRecord
from .store import load_record
from .math_utils import get_embedding, cosine_similarity, calculate_keyword_overlap

# When sentence-transformers is not installed, fall back to keyword overlap so
# Run Shortlist still produces a useful ranking in demos / lightweight envs.
try:
    from .math_utils import SentenceTransformer as _ST  # type: ignore
    _EMBEDDINGS_AVAILABLE = _ST is not None
except ImportError:
    _EMBEDDINGS_AVAILABLE = False
from .security import anonymize_candidate_record, rehydrate_text
from .compliance import record_block_reasons


# Number of candidates passed from embedding stage into LLM rerank.
# Wider funnel = better semantic recall, more LLM calls.
# Override via RERANK_FUNNEL_SIZE env var or the app config.
DEFAULT_RERANK_FUNNEL_SIZE = int(os.getenv("RERANK_FUNNEL_SIZE", "15"))

DEFAULT_RERANK_MODEL = "gemini-2.5-pro"


def _scoring_weights(req: RequirementRecord) -> Dict[str, float]:
    """
    Return a weight map for structured scoring dimensions.
    """
    return {
        "skills":     0.45,
        "seniority":  0.25,
        "experience": 0.15,
        "location":   0.10,
        "languages":  0.05,
    }


def _seniority_score(candidate_level: str, req_level: str) -> float:
    """
    Return a [0, 1] score based on seniority alignment.
    Adjacent levels score 0.7, two-off score 0.4, opposite ends score 0.1.
    """
    LEVELS = ["Intern", "Junior", "Mid", "Senior", "Lead"]
    try:
        ci = LEVELS.index(candidate_level)
        ri = LEVELS.index(req_level)
    except ValueError:
        return 0.5  # unknown seniority — neutral
    diff = abs(ci - ri)
    return [1.0, 0.7, 0.4, 0.2, 0.1][min(diff, 4)]


def score_structured(
    record: CandidateRecord,
    req: RequirementRecord,
    keyword_evidence: Dict[str, Any],
) -> float:
    """
    Compute a 0-1 structured dimension score for a single candidate.
    Does NOT use keyword frequency for ranking — keywords are in `evidence` only.
    """
    weights = _scoring_weights(req)
    scores: Dict[str, float] = {}

    # --- Skills: keyword overlap as a proxy ---
    must = set(s.lower() for s in (req.requirements.get("must_have") or []))
    nice = set(s.lower() for s in (req.requirements.get("nice_to_have") or []))
    cand_skills = set(s.lower() for s in (record.profile.technologies_used or []))

    if must:
        must_overlap = len(must & cand_skills) / len(must)
    else:
        must_overlap = 0.5  # no hard requirements — neutral
    if nice:
        nice_overlap = len(nice & cand_skills) / len(nice)
    else:
        nice_overlap = 0.5
    scores["skills"] = 0.7 * must_overlap + 0.3 * nice_overlap

    # --- Seniority ---
    req_seniority = req.requirements.get("seniority")
    if req_seniority and record.profile.seniority:
        scores["seniority"] = _seniority_score(record.profile.seniority, req_seniority)
    else:
        scores["seniority"] = 0.5

    # --- Experience ---
    req_yoe = req.requirements.get("years_of_experience")
    cand_yoe = record.profile.years_of_experience
    if req_yoe and cand_yoe is not None:
        if cand_yoe >= req_yoe:
            scores["experience"] = 1.0
        else:
            scores["experience"] = max(0.0, cand_yoe / req_yoe)
    else:
        scores["experience"] = 0.5

    # --- Location ---
    req_location = (req.requirements.get("location") or "").strip().lower()
    is_wildcard_location = req_location in ("", "remote", "anywhere", "worldwide")
    if is_wildcard_location:
        scores["location"] = 1.0
    elif record.profile.location:
        scores["location"] = 1.0 if req_location in record.profile.location.lower() else 0.0
    else:
        scores["location"] = 0.5  # unknown location — neutral, not perfect

    # --- Languages ---
    req_langs = [l.lower() for l in (req.requirements.get("languages") or [])]
    if not req_langs:
        scores["languages"] = 1.0
    else:
        cand_langs = [l.lower() for l in (record.profile.languages_spoken or [])]
        overlap = len(set(req_langs) & set(cand_langs))
        scores["languages"] = overlap / len(req_langs)

    return sum(scores[k] * weights[k] for k in weights)


def filter_candidates(
    req: RequirementRecord,
) -> List[str]:
    """
    Stage 1: Hard compliance + location gate. Returns list of record_ids.
    """
    if not RECORDS_DIR.exists():
        return []

    req_location = (req.requirements.get("location") or "").strip().lower()
    is_wildcard_location = req_location in ("", "remote", "anywhere", "worldwide")

    passing = []
    for path in RECORDS_DIR.glob("*.json"):
        record_id = path.stem
        try:
            record = load_record(record_id)
        except Exception:
            continue

        # Compliance gate
        block_reasons = record_block_reasons(record)
        if block_reasons:
            continue

        # Archived gate
        if record.state and record.state.archived:
            continue

        # Location filter — only applied when job has a specific location
        if req_location and not is_wildcard_location:
            if record.profile.location is None:
                # Policy: treat unknown location as a soft pass at filter stage;
                # score_structured will assign a neutral 0.5 for location.
                pass
            elif req_location not in record.profile.location.lower():
                continue

        passing.append(record_id)

    return passing


def build_candidate_profile_text(record: CandidateRecord) -> str:
    """
    Build a human-readable summary of a candidate for embedding / LLM prompt.
    """
    parts = []
    if record.profile.headline:
        parts.append(record.profile.headline)
    if record.profile.summary:
        parts.append(record.profile.summary)
    if record.profile.seniority:
        parts.append(f"Level: {record.profile.seniority}")
    if record.profile.years_of_experience is not None:
        parts.append(f"Experience: {record.profile.years_of_experience} years")
    if record.profile.technologies_used:
        parts.append("Skills: " + ", ".join(record.profile.technologies_used[:25]))
    if record.profile.previous_jobs:
        parts.append("Jobs: " + " | ".join(record.profile.previous_jobs[:5]))
    if record.profile.location:
        parts.append(f"Location: {record.profile.location}")
    if record.profile.languages_spoken:
        parts.append("Languages: " + ", ".join(record.profile.languages_spoken))
    return "\n".join(parts)


def build_job_text(req: RequirementRecord) -> str:
    """Build a human-readable summary of a job requirement for embedding."""
    parts = [req.title or ""]
    if req.description:
        parts.append(req.description[:500])
    reqs = req.requirements or {}
    if reqs.get("must_have"):
        parts.append("Must have: " + ", ".join(reqs["must_have"]))
    if reqs.get("nice_to_have"):
        parts.append("Nice to have: " + ", ".join(reqs["nice_to_have"]))
    if reqs.get("seniority"):
        parts.append(f"Seniority: {reqs['seniority']}")
    if reqs.get("location"):
        parts.append(f"Location: {reqs['location']}")
    return "\n".join(p for p in parts if p)


def llm_rerank_candidates(
    req: RequirementRecord,
    candidates: List[Dict[str, Any]],
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Stage 4: LLM rerank — deep contextual reasoning over the funnel.
    Returns candidates sorted by LLM match_score descending.
    """
    use_local = get_use_local_llm()

    llm_route_ok = use_local or (ENABLE_EXTERNAL_LLM and (GEMINI_API_KEY or get_active_api_key()))
    if not llm_route_ok:
        return sorted(candidates, key=lambda c: c.get("embedding_score", 0), reverse=True)[:top_n]

    job_text = build_job_text(req)
    reranked = []

    for cand in candidates:
        record_id = cand["record_id"]
        try:
            record = load_record(record_id)
        except Exception:
            cand["llm_score"] = cand.get("embedding_score", 0.0)
            reranked.append(cand)
            continue

        anon = anonymize_candidate_record(record)
        cand_text = build_candidate_profile_text(record)

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise talent evaluator. Score how well this candidate "
                    "matches the job. Return JSON only: "
                    '{"match_score": 0.0-1.0, "evidence": ["..."], "uncertainty_flags": ["..."]}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"JOB:\n{job_text}\n\nCANDIDATE (anonymized):\n{anon.anonymized_text}\n\n"
                    "Rate the match. Be precise. If key information is missing, flag it."
                ),
            },
        ]

        try:
            if use_local:
                from .extract import _lm_studio_rerank
                raw = _lm_studio_rerank(prompt_messages)
            else:
                if not _configure_genai():
                    raise ValueError("No API key")
                model = genai.GenerativeModel(
                    model_name=get_active_model(DEFAULT_RERANK_MODEL),
                    generation_config={"response_mime_type": "application/json"},
                )
                response = model.generate_content(
                    f"JOB:\n{job_text}\n\nCANDIDATE (anonymized):\n{anon.anonymized_text}\n\n"
                    "Rate the match. Return JSON: "
                    '{"match_score": 0.0-1.0, "evidence": ["..."], "uncertainty_flags": ["..."]}'
                )
                raw = response.text

            result = json.loads(raw)
            cand["llm_score"] = float(result.get("match_score", 0.5))
            cand["evidence"] = result.get("evidence", [])
            cand["uncertainty_flags"] = result.get("uncertainty_flags", [])
        except Exception as e:
            print(f"[match] LLM rerank failed for {record_id}: {e}")
            cand["llm_score"] = cand.get("embedding_score", 0.0)

        reranked.append(cand)

    return sorted(reranked, key=lambda c: c.get("llm_score", 0), reverse=True)[:top_n]


def _configure_genai() -> bool:
    key = get_active_api_key()
    if not key:
        return False
    genai.configure(api_key=key)
    return True


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
    # Guard: funnel must be at least as large as the number of results requested.
    if funnel_size < top_n:
        import warnings
        warnings.warn(
            f"funnel_size ({funnel_size}) < top_n ({top_n}); clamping funnel_size to top_n.",
            stacklevel=2,
        )
        funnel_size = top_n

    req_path = REQUIREMENTS_DIR / f"{req_id}.json"
    if not req_path.exists():
        raise ValueError(f"Requirement {req_id} not found")

    req_data = json.loads(req_path.read_text(encoding="utf-8"))
    req = RequirementRecord(**req_data)

    # Stage 1 — compliance + location filter
    candidate_ids = filter_candidates(req)
    if not candidate_ids:
        return {"req_id": req_id, "total_candidates_evaluated": 0, "results": []}

    # Stage 2 — embedding similarity
    job_text = build_job_text(req)

    candidates_with_scores = []
    if _EMBEDDINGS_AVAILABLE:
        try:
            job_embedding = get_embedding(job_text)
            for record_id in candidate_ids:
                try:
                    record = load_record(record_id)
                except Exception:
                    continue
                cand_text = build_candidate_profile_text(record)
                cand_embedding = get_embedding(cand_text)
                emb_score = float(cosine_similarity(job_embedding, cand_embedding))

                keyword_evidence = calculate_keyword_overlap(
                    cand_text,
                    (req.requirements.get("must_have") or []) + (req.requirements.get("nice_to_have") or []),
                )

                candidates_with_scores.append({
                    "record_id": record_id,
                    "embedding_score": emb_score,
                    "keyword_evidence": keyword_evidence,
                })
        except Exception as e:
            print(f"[match] Embedding stage failed: {e}; falling back to keyword ranking")
            _EMBEDDINGS_AVAILABLE_local = False
        else:
            _EMBEDDINGS_AVAILABLE_local = True
    else:
        _EMBEDDINGS_AVAILABLE_local = False

    if not _EMBEDDINGS_AVAILABLE_local:
        # Fallback: rank by keyword overlap alone
        job_keywords = (
            (req.requirements.get("must_have") or []) +
            (req.requirements.get("nice_to_have") or [])
        )
        for record_id in candidate_ids:
            try:
                record = load_record(record_id)
            except Exception:
                continue
            cand_text = build_candidate_profile_text(record)
            keyword_evidence = calculate_keyword_overlap(cand_text, job_keywords)
            score = keyword_evidence.get("overlap_ratio", 0.0)
            candidates_with_scores.append({
                "record_id": record_id,
                "embedding_score": score,
                "keyword_evidence": keyword_evidence,
            })

    # Stage 3 — structured scoring multiplier
    for cand in candidates_with_scores:
        try:
            record = load_record(cand["record_id"])
            struct_score = score_structured(record, req, cand["keyword_evidence"])
            cand["structured_score"] = struct_score
            # Blend: 60% embedding, 40% structured
            cand["combined_score"] = 0.6 * cand["embedding_score"] + 0.4 * struct_score
        except Exception:
            cand["structured_score"] = 0.0
            cand["combined_score"] = cand["embedding_score"]

    # Sort by combined score, take top funnel_size for LLM rerank
    candidates_with_scores.sort(key=lambda c: c.get("combined_score", 0), reverse=True)
    funnel = candidates_with_scores[:funnel_size]

    # Stage 4 — LLM rerank
    if use_llm_rerank:
        final = llm_rerank_candidates(req, funnel, top_n=top_n)
    else:
        final = funnel[:top_n]

    # Enrich results with candidate metadata
    results = []
    for cand in final:
        record_id = cand["record_id"]
        try:
            record = load_record(record_id)
            name = record.identity.primary_name or "Unknown"
            headline = record.profile.headline or ""
            location = record.profile.location or ""
            seniority = record.profile.seniority or ""
            skills = record.profile.technologies_used or []
        except Exception:
            name = headline = location = seniority = ""
            skills = []

        results.append({
            "record_id": record_id,
            "name": name,
            "headline": headline,
            "location": location,
            "seniority": seniority,
            "skills_preview": skills[:8],
            "embedding_score": round(cand.get("embedding_score", 0), 4),
            "structured_score": round(cand.get("structured_score", 0), 4),
            "combined_score": round(cand.get("combined_score", 0), 4),
            "llm_score": round(cand.get("llm_score", cand.get("combined_score", 0)), 4),
            "evidence": cand.get("evidence", []),
            "uncertainty_flags": cand.get("uncertainty_flags", []),
            "keyword_evidence": cand.get("keyword_evidence", {}),
        })

    # Persist shortlist back to the requirement file
    req_data["shortlist"] = results
    req_data["shortlist_generated_at"] = datetime.utcnow().isoformat() + "Z"
    req_path.write_text(json.dumps(req_data, indent=2), encoding="utf-8")

    return {
        "req_id": req_id,
        "total_candidates_evaluated": len(candidate_ids),
        "funnel_size": len(funnel),
        "results": results,
    }
