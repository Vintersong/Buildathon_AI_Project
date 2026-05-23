import sys
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.match import generate_shortlist


def run_eval(eval_data_path: Path):
    """
    Run evaluation on the shortlisting module against a ground truth dataset.
    Uses LangChain's built-in scoring utilities to calculate Precision@K and
    report pass/fail against the 80% accuracy target specified in the brief.
    """
    if not eval_data_path.exists():
        print(f"Error: Eval data file {eval_data_path} not found.")
        sys.exit(1)

    with open(eval_data_path, "r", encoding="utf-8") as f:
        eval_cases = json.load(f)

    # ---------------------------------------------------------------------------
    # LangChain evaluation harness
    # ---------------------------------------------------------------------------
    try:
        from langchain.evaluation import load_evaluator
        from langchain_core.outputs import Generation
        _langchain_available = True
    except ImportError:
        _langchain_available = False
        print("Warning: langchain not installed — falling back to manual Precision@K.")

    total_expected = 0
    total_hits = 0
    lc_results = []

    print(f"Running evaluation against {len(eval_cases)} jobs...\n")

    for case in eval_cases:
        job_id = case["job_id"]
        expected = set(case["expected_top_candidates"])
        k = len(expected)

        if k == 0:
            continue

        print(f"Evaluating Job: {job_id}")

        try:
            report = generate_shortlist(job_id, top_n=max(5, k), use_llm_rerank=True)
            shortlist_ids = [c["record_id"] for c in report["shortlist"]][:k]

            hits = expected.intersection(set(shortlist_ids))
            precision = len(hits) / k

            total_expected += k
            total_hits += len(hits)

            print(f"  Expected (Top {k}): {expected}")
            print(f"  Actual   (Top {k}): {shortlist_ids}")
            print(f"  Hits: {len(hits)} / {k}  (Precision@{k}: {precision:.2f})")

            # LangChain string-distance evaluator gives a normalized similarity
            # score between the expected and actual shortlist sets.
            if _langchain_available:
                try:
                    evaluator = load_evaluator("string_distance")
                    lc_result = evaluator.evaluate_strings(
                        prediction=str(sorted(shortlist_ids)),
                        reference=str(sorted(expected)),
                    )
                    lc_results.append(lc_result)
                    print(f"  LangChain string_distance score: {lc_result.get('score', 'n/a'):.4f}")
                except Exception as lc_err:
                    print(f"  LangChain evaluator error: {lc_err}")

        except Exception as e:
            print(f"  Failed to generate shortlist: {e}")
            total_expected += k

    if total_expected > 0:
        accuracy = (total_hits / total_expected) * 100
        print(f"\n=== Overall Success Metric ===")
        print(f"Accuracy (Precision@K): {accuracy:.1f}%")
        if accuracy >= 80.0:
            print("Status: PASSED (>= 80% target)")
        else:
            print("Status: FAILED (< 80% target)")

        if lc_results:
            avg_lc = sum(r.get("score", 0) for r in lc_results) / len(lc_results)
            print(f"LangChain avg string_distance score: {avg_lc:.4f} (lower = closer match)")
    else:
        print("No valid evaluation cases found.")


if __name__ == "__main__":
    default_data_path = project_root / "tests" / "eval_data.json"
    run_eval(default_data_path)
