import argparse
import sys
import json
from pathlib import Path

# Add project root to python path to import core
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.maintenance import bulk_refresh

def main():
    parser = argparse.ArgumentParser(description="Bulk refresh candidates from a JSON updates file")
    parser.add_argument("updates_file", help="Path to a JSON file containing an array of {record_id, raw_text} objects")
    
    args = parser.parse_args()
    file_path = Path(args.updates_file)
    
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist.")
        sys.exit(1)
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            updates = json.load(f)
            
        if not isinstance(updates, list):
            print("Error: JSON file must contain a list of update objects.")
            sys.exit(1)
            
        print(f"Processing {len(updates)} updates...")
        results = bulk_refresh(updates)
        
        print("\n--- Bulk Refresh Results ---")
        print(f"Success: {results['success']}")
        print(f"Failed:  {results['failed']}")
        
        if results['errors']:
            print("\nErrors:")
            for err in results['errors']:
                print(f"  [{err['record_id']}]: {err['error']}")
                
    except Exception as e:
        print(f"Failed to process updates file: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
