"""
Bloodhound Evaluation Runner

Usage:
    python -m core.eval.run_eval [--no-llm]

Options:
    --no-llm    Skip LangChain LLM evaluation; use string matching only.
                Useful when GEMINI_API_KEY is not set.

Outputs a JSON report to stdout:
{
  "cv_extraction": { "accuracy": 0.87, "target": 0.85, "pass": true, ... },
  "candidate_matching": { "accuracy": 0.80, "target": 0.80, "pass": true, ... },
  "overall_pass": true
}

Exit code: 0 if overall_pass, 1 otherwise.
"""

from __future__ import annotations

import json
import sys

from core.eval.golden_data import GOLDEN_EXTRACTIONS, GOLDEN_MATCHES
from core.eval.eval_extraction import evaluate_extraction
from core.eval.eval_matching import evaluate_matching


def main() -> None:
    use_llm = "--no-llm" not in sys.argv

    print("Running CV extraction evaluation...", file=sys.stderr)
    ext_result = evaluate_extraction(GOLDEN_EXTRACTIONS, use_llm=use_llm)

    print("Running candidate matching evaluation...", file=sys.stderr)
    match_result = evaluate_matching(GOLDEN_MATCHES)

    report = {
        "cv_extraction": ext_result,
        "candidate_matching": match_result,
        "overall_pass": ext_result["pass"] and match_result["pass"],
    }

    print(json.dumps(report, indent=2))

    # Non-zero exit code when evaluation fails thresholds
    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    main()
