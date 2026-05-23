import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap: load .env before any core import so module-level constants see the values
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / ".env", override=True)

from core.ingest import ingest_file
from core.store import load_record


def _emit(obj: dict):
    print(json.dumps(obj), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Ingest CVs or LinkedIn exports into the Bloodhound Talent Pool")
    parser.add_argument("path", help="Path to a file or directory to ingest")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion even if hash exists")

    args = parser.parse_args()
    target_path = Path(args.path)

    if not target_path.exists():
        _emit({"event": "error", "message": f"Path does not exist: {target_path}"})
        sys.exit(1)

    files_to_process = []
    if target_path.is_file():
        files_to_process.append(target_path)
    elif target_path.is_dir():
        for ext in ["*.pdf", "*.docx", "*.txt"]:
            files_to_process.extend(target_path.glob(ext))

    if not files_to_process:
        _emit({"event": "error", "message": f"No valid documents found at {target_path}"})
        sys.exit(0)

    _emit({
        "event": "start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_files": len(files_to_process),
        "path": str(target_path),
        "force": args.force,
    })

    success, failed, skipped = 0, 0, 0
    results = []

    for f in files_to_process:
        t0 = time.monotonic()
        entry: dict = {"file": f.name}
        try:
            record_id = ingest_file(f, force=args.force)
            elapsed = round(time.monotonic() - t0, 2)
            rec = load_record(record_id)
            entry.update({
                "event": "ingested",
                "record_id": record_id,
                "elapsed_s": elapsed,
                "name": rec.identity.primary_name if rec else None,
                "seniority": rec.profile.seniority if rec else None,
                "skills": (rec.profile.technologies_used or [])[:6] if rec else [],
                "status": rec.state.status if rec else None,
                "confidence": rec.scores.extraction_confidence if rec else None,
            })
            success += 1
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            entry.update({"event": "failed", "elapsed_s": elapsed, "error": str(e)})
            failed += 1

        _emit(entry)
        results.append(entry)

    _emit({
        "event": "complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "failed": failed,
        "skipped": skipped,
    })


if __name__ == "__main__":
    main()
