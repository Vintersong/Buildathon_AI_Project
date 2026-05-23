import sys
import json
from pathlib import Path

# Add project root to python path to import core
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.match import generate_shortlist

def run_eval(eval_data_path: Path):
    """
    Run evaluation on the shortlisting module against a ground truth dataset.
    Calculates simple Precision@K accuracy metric.
    """
    if not eval_data_path.exists():
        print(f"Error: Eval data file {eval_data_path} not found.")
        sys.exit(1)
        
    with open(eval_data_path, "r", encoding="utf-8") as f:
        eval_cases = json.load(f)
        
    total_expected = 0
    total_hits = 0
    
    print(f"Running evaluation against {len(eval_cases)} jobs...\n")
    
    for case in eval_cases:
        job_id = case["job_id"]
        expected = set(case["expected_top_candidates"])
        k = len(expected)
        
        if k == 0:
            continue
            
        print(f"Evaluating Job: {job_id}")
        
        try:
            # Generate shortlist using our pipeline (disable LLM rerank to save time/cost during eval if preferred, but leaving on for full accuracy test)
            report = generate_shortlist(job_id, top_n=max(5, k), use_llm_rerank=True)
            shortlist_ids = [c["record_id"] for c in report["shortlist"]][:k]
            
            hits = expected.intersection(set(shortlist_ids))
            
            total_expected += k
            total_hits += len(hits)
            
            print(f"  Expected (Top {k}): {expected}")
            print(f"  Actual   (Top {k}): {shortlist_ids}")
            print(f"  Hits: {len(hits)} / {k}")
            
        except Exception as e:
            print(f"  Failed to generate shortlist: {e}")
            total_expected += k
            
    if total_expected > 0:
        accuracy = (total_hits / total_expected) * 100
        print(f"\n=== Overall Success Metric ===")
        print(f"Accuracy (Precision@{k}): {accuracy:.1f}%")
        if accuracy >= 80.0:
            print("Status: PASSED (>= 80% target)")
        else:
            print("Status: FAILED (< 80% target)")
    else:
        print("No valid evaluation cases found.")

if __name__ == "__main__":
    default_data_path = project_root / "tests" / "eval_data.json"
    run_eval(default_data_path)
