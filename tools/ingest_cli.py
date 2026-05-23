import argparse
import sys
from pathlib import Path

# Add project root to python path to import core
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.ingest import ingest_file

def main():
    parser = argparse.ArgumentParser(description="Ingest CVs or LinkedIn exports into the Bloodhound Talent Pool")
    parser.add_argument("path", help="Path to a file or directory to ingest")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion even if hash exists")
    
    args = parser.parse_args()
    target_path = Path(args.path)
    
    if not target_path.exists():
        print(f"Error: Path {target_path} does not exist.")
        sys.exit(1)
        
    files_to_process = []
    if target_path.is_file():
        files_to_process.append(target_path)
    elif target_path.is_dir():
        for ext in ["*.pdf", "*.docx", "*.txt"]:
            files_to_process.extend(target_path.glob(ext))
            
    if not files_to_process:
        print(f"No valid documents found at {target_path}")
        sys.exit(0)
        
    success_count = 0
    fail_count = 0
    
    for f in files_to_process:
        print(f"Ingesting {f.name}...")
        try:
            record_id = ingest_file(f, force=args.force)
            success_count += 1
        except Exception as e:
            print(f"Failed to ingest {f.name}: {str(e)}")
            fail_count += 1
            
    print(f"\nIngestion complete: {success_count} succeeded, {fail_count} failed.")

if __name__ == "__main__":
    main()
