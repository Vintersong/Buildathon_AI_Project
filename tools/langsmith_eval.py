"""
LangSmith evaluation harness for Bloodhound.

Runs two eval suites against pre-built golden datasets:
  1. CV extraction accuracy  — seniority exact match, skill recall, YOE ±1yr
  2. Candidate match ranking — does score_structured rank the expected winner #1?

Usage:
    LANGCHAIN_API_KEY=<key> python tools/langsmith_eval.py
    LANGCHAIN_API_KEY=<key> python tools/langsmith_eval.py --suite extraction
    LANGCHAIN_API_KEY=<key> python tools/langsmith_eval.py --suite matching

Datasets are created on first run and reused on subsequent runs.

NOTE: The extraction suite tests whichever LLM backend is currently active.
  If ENABLE_EXTERNAL_LLM=False (no key set), it tests the heuristic fallback,
  not the LLM extraction path. Set a provider API key in .secrets.json or via
  env vars to evaluate LLM-based extraction.
"""

import os
import sys
import argparse
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.eval.golden_data import GOLDEN_EXTRACTIONS, GOLDEN_MATCHES
from core.schemas import (
    CandidateRecord,
    Profile,
    RequirementRecord,
    RequirementCriteria,
)

EXTRACTION_DATASET = "bloodhound-cv-extractions"
MATCHING_DATASET = "bloodhound-candidate-matching"

_DUMMY_TS = "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

def _ensure_extraction_dataset(client) -> str:
    """Create or reuse the CV-extraction golden dataset in LangSmith."""
    # TODO: replace bare except with client.has_dataset() once SDK stabilises
    try:
        ds = client.read_dataset(dataset_name=EXTRACTION_DATASET)
        print(f"[langsmith] Reusing existing dataset: {EXTRACTION_DATASET}")
        return str(ds.id)
    except Exception:
        pass

    ds = client.create_dataset(
        EXTRACTION_DATASET,
        description="Golden CV extraction cases — seniority, skills, YOE",
    )
    inputs = [{"cv_text": c["cv_text"]} for c in GOLDEN_EXTRACTIONS]
    outputs = [c["expected"] for c in GOLDEN_EXTRACTIONS]
    client.create_examples(inputs=inputs, outputs=outputs, dataset_id=ds.id)
    print(f"[langsmith] Created '{EXTRACTION_DATASET}' with {len(inputs)} examples")
    return str(ds.id)


def _ensure_matching_dataset(client) -> str:
    """Create or reuse the candidate-matching golden dataset in LangSmith."""
    try:
        ds = client.read_dataset(dataset_name=MATCHING_DATASET)
        print(f"[langsmith] Reusing existing dataset: {MATCHING_DATASET}")
        return str(ds.id)
    except Exception:
        pass

    ds = client.create_dataset(
        MATCHING_DATASET,
        description="Golden candidate-matching cases — top-1 accuracy for score_structured",
    )
    inputs, outputs = [], []
    for case in GOLDEN_MATCHES:
        winner_idx = case["expected_winner_index"]
        inputs.append({
            "description": case["description"],
            "requirement": case["requirement"],
            "candidates": case["candidates"],
        })
        outputs.append({
            "expected_winner_index": winner_idx,
            "expected_winner_id": case["candidates"][winner_idx]["id"],
        })
    client.create_examples(inputs=inputs, outputs=outputs, dataset_id=ds.id)
    print(f"[langsmith] Created '{MATCHING_DATASET}' with {len(inputs)} examples")
    return str(ds.id)


# ---------------------------------------------------------------------------
# Target functions (called once per dataset example by evaluate())
# ---------------------------------------------------------------------------

def extraction_target(inputs: dict) -> dict:
    """Run CV extraction and return the fields checked by golden expectations."""
    from core.extract import extract_candidate_data

    extraction, _ = extract_candidate_data(inputs["cv_text"])
    return {
        "seniority": extraction.seniority,
        "technologies_used": [s.lower() for s in (extraction.technologies_used or [])],
        "years_of_experience": extraction.years_of_experience,
    }


def _record_from_golden_candidate(c: dict) -> CandidateRecord:
    """Build a minimal CandidateRecord from a golden-data candidate dict."""
    return CandidateRecord(
        created_at=_DUMMY_TS,
        updated_at=_DUMMY_TS,
        profile=Profile(
            seniority=c.get("seniority"),
            technologies_used=c.get("skills", []),
            years_of_experience=c.get("experience"),
            location=c.get("location"),
        ),
    )


def _req_from_golden(r: dict) -> RequirementRecord:
    """Build a RequirementRecord from a golden-data requirement dict.

    Note: golden requirements omit seniority / years_of_experience, so those
    scoring dimensions will return 0.5 (neutral). Skill overlap is the decisive
    signal; all cases set location=None (wildcard → 1.0), so results are
    deterministic on skills alone.
    """
    return RequirementRecord(
        id=r["id"],
        title=r["title"],
        created_at=_DUMMY_TS,
        updated_at=_DUMMY_TS,
        requirements=RequirementCriteria(
            must_have=r.get("must_have", []),
            nice_to_have=r.get("nice_to_have", []),
            location=r.get("location"),
        ),
    )


def matching_target(inputs: dict) -> dict:
    """Score each candidate with score_structured and return the ranked results."""
    from core.match import score_structured

    req_record = _req_from_golden(inputs["requirement"])
    scored = []
    for c in inputs["candidates"]:
        record = _record_from_golden_candidate(c)
        # keyword_evidence is in score_structured's signature but unused in the
        # function body — the score is computed from profile fields directly.
        score = score_structured(record, req_record, {})
        scored.append({"id": c["id"], "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "ranked_ids": [x["id"] for x in scored],
        "top_id": scored[0]["id"] if scored else None,
        "scores": {x["id"]: round(x["score"], 4) for x in scored},
    }


# ---------------------------------------------------------------------------
# Evaluators (outputs, reference_outputs) -> {"key": str, "score": float}
# ---------------------------------------------------------------------------

def eval_seniority_exact(outputs: dict, reference_outputs: dict) -> dict:
    """1.0 if predicted seniority matches the expected label exactly."""
    predicted = (outputs.get("seniority") or "").strip()
    expected = (reference_outputs.get("seniority") or "").strip()
    return {"key": "seniority_exact", "score": float(predicted == expected)}


def eval_skill_recall(outputs: dict, reference_outputs: dict) -> dict:
    """Fraction of expected skills found in the predicted skill set (case-insensitive)."""
    predicted = set(s.lower() for s in (outputs.get("technologies_used") or []))
    expected = set(s.lower() for s in (reference_outputs.get("technologies_used") or []))
    if not expected:
        return {"key": "skill_recall", "score": 1.0}
    score = len(predicted & expected) / len(expected)
    return {"key": "skill_recall", "score": round(score, 4)}


def eval_yoe_tolerance(outputs: dict, reference_outputs: dict) -> dict:
    """1.0 if predicted years-of-experience is within 1 year of expected."""
    predicted = outputs.get("years_of_experience")
    expected = reference_outputs.get("years_of_experience")
    if predicted is None or expected is None:
        return {"key": "yoe_within_1yr", "score": 0.0}
    return {"key": "yoe_within_1yr", "score": float(abs(predicted - expected) <= 1)}


def eval_winner_top1(outputs: dict, reference_outputs: dict) -> dict:
    """1.0 if the top-ranked candidate matches the expected winner."""
    return {
        "key": "winner_top1_correct",
        "score": float(outputs.get("top_id") == reference_outputs.get("expected_winner_id")),
    }


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(results, suite_name: str) -> None:
    scores: dict[str, list[float]] = defaultdict(list)
    try:
        for row in results:
            for res in row.evaluation_results.results:
                if res.score is not None:
                    scores[res.key].append(float(res.score))
    except Exception:
        print("  (Unable to parse result rows — view full results in LangSmith UI)")
        return

    print(f"\n=== {suite_name} Eval Summary ===")
    if not scores:
        print("  (No scores found — check LangSmith UI for trace errors)")
        return

    for key in sorted(scores):
        avg = sum(scores[key]) / len(scores[key])
        n = len(scores[key])
        status = "PASS" if avg >= 0.8 else "FAIL"
        print(f"  {key}: {avg:.1%}  (n={n})  [{status}]")


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------

def run_extraction_eval(client, experiment_prefix: str = "cv-extraction") -> None:
    from langsmith.evaluation import evaluate

    dataset_id = _ensure_extraction_dataset(client)
    print(f"\n[eval] Running extraction suite on '{EXTRACTION_DATASET}'...")
    results = evaluate(
        extraction_target,
        data=dataset_id,
        evaluators=[eval_seniority_exact, eval_skill_recall, eval_yoe_tolerance],
        experiment_prefix=experiment_prefix,
        max_concurrency=2,
    )
    _print_summary(results, "Extraction")


def run_matching_eval(client, experiment_prefix: str = "candidate-matching") -> None:
    from langsmith.evaluation import evaluate

    dataset_id = _ensure_matching_dataset(client)
    print(f"\n[eval] Running matching suite on '{MATCHING_DATASET}'...")
    results = evaluate(
        matching_target,
        data=dataset_id,
        evaluators=[eval_winner_top1],
        experiment_prefix=experiment_prefix,
        max_concurrency=4,
    )
    _print_summary(results, "Matching")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LangSmith eval harness for Bloodhound")
    parser.add_argument(
        "--suite",
        choices=["extraction", "matching", "all"],
        default="all",
        help="Which eval suite to run (default: all)",
    )
    args = parser.parse_args()

    if not os.getenv("LANGCHAIN_API_KEY"):
        print(
            "Error: LANGCHAIN_API_KEY env var not set.\n"
            "Get a key at https://smith.langchain.com/ → Settings → API Keys"
        )
        sys.exit(1)

    from langsmith import Client
    client = Client()

    if args.suite in ("extraction", "all"):
        run_extraction_eval(client)
    if args.suite in ("matching", "all"):
        run_matching_eval(client)
