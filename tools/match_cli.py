import argparse
import sys
import json
from pathlib import Path

# Add project root to python path to import core
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.match import generate_shortlist

def main():
    parser = argparse.ArgumentParser(description="Match candidates against a job requirement")
    parser.add_argument("--job", required=True, help="ID of the requirement record")
    parser.add_argument("--top", type=int, default=5, help="Number of candidates to shortlist")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM reranking (faster, local only)")
    
    args = parser.parse_args()
    
    print(f"Generating shortlist for job {args.job}...")
    try:
        report = generate_shortlist(args.job, top_n=args.top, use_llm_rerank=not args.no_llm)
        print("\n--- Shortlist Report ---")
        print(json.dumps(report, indent=2))
    except Exception as e:
        print(f"Failed to generate shortlist: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
