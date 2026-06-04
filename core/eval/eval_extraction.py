"""
CV extraction accuracy evaluator.

Uses the configured provider as an optional LLM-as-judge when available,
otherwise falls back to deterministic string matching.

Accuracy is computed per-field across all golden cases:
  - 'seniority': lowercase substring match
  - 'technologies_used': fraction of expected skills present in extracted list
  - 'years_of_experience': within +/- 1 year tolerance

Target: >= 0.85 overall accuracy.
"""

from __future__ import annotations

import json
from typing import Any

from core import llm as app_llm
from core.extract import extract_candidate_data, extract_candidate_data_heuristic


def _seniority_match(predicted: str | None, expected: str) -> float:
    if not predicted:
        return 0.0
    return 1.0 if expected.lower() in predicted.lower() else 0.0


def _skills_match(predicted: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    predicted_lower = {s.lower() for s in (predicted or [])}
    hits = sum(1 for e in expected if e.lower() in predicted_lower)
    return hits / len(expected)


def _experience_match(predicted: int | None, expected: int) -> float:
    if predicted is None:
        return 0.0
    return 1.0 if abs(predicted - expected) <= 1 else 0.0


def _eval_with_llm(predicted_str: str, expected_str: str, field: str) -> float:
    """Configured-provider LLM-as-judge evaluation for a single field."""
    try:
        raw = app_llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are evaluating a CV parser. Respond with only JSON "
                        "matching {\"score\": number}, where score is 1 for "
                        "correct, 0.5 for partially correct, and 0 for incorrect."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Field: {field}\n"
                        f"Expected: {expected_str}\n"
                        f"Predicted: {predicted_str}"
                    ),
                },
            ],
            json_mode=True,
            temperature=0,
        )
        result = json.loads(raw)
        score = float(result.get("score", 0))
        return min(1.0, max(0.0, score))
    except Exception:
        return -1.0  # sentinel: caller falls back to string match


# Fields that the local regex extractor handles reliably (no LLM required)
_LOCAL_FIELDS = {"seniority", "technologies_used"}
# Fields that require LLM-based extraction to be accurate
_LLM_ONLY_FIELDS = {"years_of_experience"}


def evaluate_extraction(
    golden_cases: list[dict[str, Any]],
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """
    Evaluate CV extraction accuracy against golden_cases.

    When use_llm=False, only fields in _LOCAL_FIELDS are evaluated.
    When use_llm=True, all fields including _LLM_ONLY_FIELDS are evaluated.

    Args:
        golden_cases: list from golden_data.GOLDEN_EXTRACTIONS
        use_llm: force LLM evaluation (True/False). Default: auto-detect.

    Returns:
        dict with keys: accuracy, target, pass, per_field, details, llm_mode
    """
    if use_llm is None:
        use_llm = app_llm.llm_available()

    results: list[dict[str, Any]] = []

    for case in golden_cases:
        cv_text: str = case["cv_text"]
        expected: dict = case["expected"]

        try:
            if use_llm:
                extraction, _ = extract_candidate_data(cv_text)
            else:
                extraction, _ = extract_candidate_data_heuristic(cv_text)
        except Exception as exc:
            for field in expected:
                results.append({"field": field, "score": 0.0, "error": str(exc)})
            continue

        for field, exp_val in expected.items():
            if not use_llm and field in _LLM_ONLY_FIELDS:
                continue
            score: float

            if field == "seniority":
                predicted = getattr(extraction, "seniority", None)
                if use_llm:
                    llm_score = _eval_with_llm(str(predicted), str(exp_val), field)
                    score = llm_score if llm_score >= 0 else _seniority_match(predicted, exp_val)
                else:
                    score = _seniority_match(predicted, exp_val)

            elif field == "technologies_used":
                predicted_list: list[str] = getattr(extraction, "technologies_used", []) or []
                score = _skills_match(predicted_list, exp_val)

            elif field == "years_of_experience":
                predicted_years = getattr(extraction, "years_of_experience", None)
                score = _experience_match(predicted_years, exp_val)

            else:
                predicted = getattr(extraction, field, None)
                if use_llm:
                    llm_score = _eval_with_llm(str(predicted), str(exp_val), field)
                    score = llm_score if llm_score >= 0 else (1.0 if str(predicted) == str(exp_val) else 0.0)
                else:
                    score = 1.0 if str(predicted) == str(exp_val) else 0.0

            results.append({"field": field, "score": score})

    if not results:
        return {"accuracy": 0.0, "target": 0.85, "pass": False, "per_field": {}, "details": []}

    overall = sum(r["score"] for r in results) / len(results)

    per_field: dict[str, list[float]] = {}
    for r in results:
        per_field.setdefault(r["field"], []).append(r["score"])
    per_field_avg = {f: round(sum(v) / len(v), 3) for f, v in per_field.items()}

    return {
        "accuracy": round(overall, 3),
        "target": 0.85,
        "pass": overall >= 0.85,
        "per_field": per_field_avg,
        "details": results,
        "llm_mode": use_llm,
    }
