"""
LangChain-backed binary candidate-role matching evaluation.

Usage:
    python -m tools.eval_candidates
    python -m tools.eval_candidates --data tests/data/candidate_role_eval.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from langchain_core.runnables import RunnableLambda

from core.candidate_role_eval import match_candidate_to_role, normalize_match_label


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "tests" / "data" / "candidate_role_eval.csv"
DEFAULT_TARGET = 0.80
REQUIRED_COLUMNS = {"candidate_profile", "role_description", "ground_truth_label"}


@dataclass(frozen=True)
class CandidateRoleEvalExample:
    row_number: int
    candidate_profile: str
    role_description: str
    ground_truth_label: str


def load_eval_dataset(path: Path) -> list[CandidateRoleEvalExample]:
    """Load and validate candidate-role eval rows from CSV."""
    if not path.exists():
        raise FileNotFoundError(f"Eval dataset not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"Eval dataset missing required columns: {', '.join(missing)}")

        examples: list[CandidateRoleEvalExample] = []
        for row_number, row in enumerate(reader, start=2):
            expected = normalize_match_label(row.get("ground_truth_label"))
            if expected is None:
                raise ValueError(
                    f"Row {row_number} has invalid ground_truth_label: {row.get('ground_truth_label')!r}"
                )
            candidate_profile = (row.get("candidate_profile") or "").strip()
            role_description = (row.get("role_description") or "").strip()
            if not candidate_profile or not role_description:
                raise ValueError(f"Row {row_number} must include candidate_profile and role_description")
            examples.append(
                CandidateRoleEvalExample(
                    row_number=row_number,
                    candidate_profile=candidate_profile,
                    role_description=role_description,
                    ground_truth_label=expected,
                )
            )

    return examples


def run_predictions(examples: Sequence[CandidateRoleEvalExample]) -> list[str]:
    """Run examples through a LangChain RunnableLambda wrapper."""
    matcher = RunnableLambda(
        lambda payload: match_candidate_to_role(
            payload["candidate_profile"],
            payload["role_description"],
        )
    )
    payloads = [
        {
            "candidate_profile": example.candidate_profile,
            "role_description": example.role_description,
        }
        for example in examples
    ]
    return list(matcher.batch(payloads, config={"max_concurrency": 2}))


def build_report(
    examples: Sequence[CandidateRoleEvalExample],
    predictions: Sequence[object],
    target: float = DEFAULT_TARGET,
) -> dict:
    if len(examples) != len(predictions):
        raise ValueError("Examples and predictions must have the same length")

    total = len(examples)
    correct = 0
    per_class = {
        "match": {"correct": 0, "total": 0, "accuracy": 0.0},
        "no_match": {"correct": 0, "total": 0, "accuracy": 0.0},
    }
    failures = []

    for example, raw_prediction in zip(examples, predictions):
        expected = example.ground_truth_label
        predicted = normalize_match_label(raw_prediction)
        is_correct = predicted == expected

        per_class[expected]["total"] += 1
        if is_correct:
            correct += 1
            per_class[expected]["correct"] += 1
        else:
            failures.append(
                {
                    "row_number": example.row_number,
                    "expected": expected,
                    "predicted": predicted or "invalid",
                    "raw_prediction": str(raw_prediction),
                    "candidate_profile": _truncate(example.candidate_profile),
                    "role_description": _truncate(example.role_description),
                }
            )

    for stats in per_class.values():
        stats["accuracy"] = round(stats["correct"] / stats["total"], 4) if stats["total"] else 0.0

    accuracy = correct / total if total else 0.0
    return {
        "dataset": str(DEFAULT_DATA_PATH),
        "metric": "exact_match_accuracy",
        "label_space": ["match", "no_match"],
        "accuracy": round(accuracy, 4),
        "target": target,
        "pass": accuracy >= target,
        "correct": correct,
        "total": total,
        "per_class": per_class,
        "failed_examples": failures,
    }


def evaluate_dataset(path: Path = DEFAULT_DATA_PATH, target: float = DEFAULT_TARGET, limit: int | None = None) -> dict:
    examples = load_eval_dataset(path)
    if limit is not None:
        examples = examples[:limit]
    predictions = run_predictions(examples)
    report = build_report(examples, predictions, target=target)
    report["dataset"] = str(path)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate binary candidate-role matching accuracy.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="CSV dataset path.")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET, help="Required accuracy threshold.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of examples to evaluate (default: all).")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = evaluate_dataset(args.data, target=args.target, limit=args.limit)
    except Exception as exc:
        print(f"Candidate-role eval failed to start: {exc}", file=sys.stderr)
        return 2

    indent = None if args.compact else 2
    print(json.dumps(report, indent=indent))
    return 0 if report["pass"] else 1


def _truncate(value: str, limit: int = 220) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


if __name__ == "__main__":
    sys.exit(main())
