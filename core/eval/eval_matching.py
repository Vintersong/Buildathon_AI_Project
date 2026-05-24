"""
Candidate–role matching accuracy evaluator.

Tests the core scoring functions directly (no file I/O) by constructing
in-memory CandidateRecord and RequirementRecord objects and running the
same weighted scoring pipeline used in core.match.generate_shortlist.

Metric: top-1 hit rate (does the expected winner score highest?)
Target: >= 0.80 (80 % of test cases rank the correct candidate first).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.schemas import (
    CandidateRecord,
    Identity,
    Profile,
    State,
    Compliance,
    Scores,
    RequirementRecord,
    RequirementCriteria,
)
from core.match import score_keywords, score_structured, _scoring_weights


def _build_candidate(c: dict[str, Any]) -> CandidateRecord:
    """Construct a CandidateRecord from a minimal eval dict."""
    now = datetime.now(timezone.utc).isoformat()
    return CandidateRecord(
        created_at=now,
        updated_at=now,
        identity=Identity(primary_name=c["id"]),
        profile=Profile(
            seniority=c.get("seniority"),
            years_of_experience=c.get("experience"),
            technologies_used=c.get("skills", []),
            location=c.get("location"),
        ),
        state=State(last_refreshed_at=now),
        scores=Scores(),
        compliance=Compliance(data_region="EEA"),
    )


def _build_requirement(req: dict[str, Any]) -> RequirementRecord:
    """Construct a RequirementRecord from a minimal eval dict."""
    now = datetime.now(timezone.utc).isoformat()
    return RequirementRecord(
        id=req["id"],
        title=req["title"],
        created_at=now,
        updated_at=now,
        requirements=RequirementCriteria(
            must_have=req.get("must_have", []),
            nice_to_have=req.get("nice_to_have", []),
            location=req.get("location"),
        ),
    )


def _score_candidate(
    candidate_id: str,
    record: CandidateRecord,
    req: RequirementRecord,
) -> float:
    kw = score_keywords([candidate_id], req)
    structured = score_structured([candidate_id], req)
    weights = _scoring_weights(req)

    skills_score = kw.get(candidate_id, 0.0)
    s = structured.get(candidate_id, {})
    return (
        skills_score * weights.get("skills", 1.0)
        + s.get("experience", 0.0) * weights.get("experience", 0.0)
        + s.get("location", 0.0) * weights.get("location", 0.0)
        + s.get("language", 0.0) * weights.get("language", 0.0)
        + s.get("freshness", 0.0) * weights.get("freshness", 0.0)
    )


def evaluate_matching(golden_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Evaluate matching accuracy against golden_cases.

    Args:
        golden_cases: list from golden_data.GOLDEN_MATCHES

    Returns:
        dict with keys: accuracy, target, pass, details
    """
    hits = 0
    details: list[dict[str, Any]] = []

    for case in golden_cases:
        req_data = case["requirement"]
        candidates_data = case["candidates"]
        expected_winner_index = case["expected_winner_index"]
        expected_winner_id = candidates_data[expected_winner_index]["id"]

        req = _build_requirement(req_data)

        # Build in-memory records keyed by their id
        records: dict[str, CandidateRecord] = {}
        for c in candidates_data:
            records[c["id"]] = _build_candidate(c)

        # Temporarily monkey-patch load_record so score_* functions can load
        # our in-memory records without touching the file system
        import core.match as match_module
        original_load = match_module.load_record

        def _mock_load(record_id: str):
            return records.get(record_id)

        match_module.load_record = _mock_load  # type: ignore[assignment]
        try:
            scores = {
                cid: _score_candidate(cid, rec, req)
                for cid, rec in records.items()
            }
        finally:
            match_module.load_record = original_load  # type: ignore[assignment]

        ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        top_candidate = ranked[0] if ranked else None
        hit = top_candidate == expected_winner_id

        if hit:
            hits += 1

        details.append({
            "description": case.get("description", req_data["title"]),
            "expected_winner": expected_winner_id,
            "actual_winner": top_candidate,
            "scores": {k: round(v, 3) for k, v in scores.items()},
            "pass": hit,
        })

    total = len(golden_cases)
    accuracy = hits / total if total else 0.0

    return {
        "accuracy": round(accuracy, 3),
        "target": 0.80,
        "pass": accuracy >= 0.80,
        "hits": hits,
        "total": total,
        "details": details,
    }
