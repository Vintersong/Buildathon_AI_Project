import sys
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.maintenance import archive_expired_records

def main():
    result = archive_expired_records()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
