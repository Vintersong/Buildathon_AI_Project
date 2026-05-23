"""CLI tool: list stale candidates (not refreshed in N months) and optionally trigger bulk_refresh.

Usage:
    python tools/stale_refresh_cli.py               # list stale record IDs
    python tools/stale_refresh_cli.py --months 3    # use custom threshold
"""
import sys
import json
import argparse
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.maintenance import find_stale_candidates
from core.config import STALE_REFRESH_MONTHS


def main():
    parser = argparse.ArgumentParser(description="List candidates that need a profile refresh.")
    parser.add_argument(
        "--months",
        type=int,
        default=STALE_REFRESH_MONTHS,
        help=f"Months since last refresh before a candidate is considered stale (default: {STALE_REFRESH_MONTHS})"
    )
    args = parser.parse_args()

    stale = find_stale_candidates(months=args.months)

    print(json.dumps({
        "stale_count": len(stale),
        "threshold_months": args.months,
        "record_ids": stale
    }, indent=2))


if __name__ == "__main__":
    main()
