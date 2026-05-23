import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base project directory
BASE_DIR = Path(__file__).parent.parent

# Storage paths
RECORDS_DIR = BASE_DIR / "records"
REQUIREMENTS_DIR = BASE_DIR / "requirements"
INDEXES_DIR = BASE_DIR / "indexes"
LOGS_DIR = BASE_DIR / "logs"
POLICIES_DIR = BASE_DIR / "policies"
QUARANTINE_DIR = BASE_DIR / "quarantine"

# Intake paths
INTAKE_DIR = BASE_DIR / "intake"
CVS_DIR = INTAKE_DIR / "cvs"
LINKEDIN_DIR = INTAKE_DIR / "linkedin"

# Specific file paths
EVENTS_LOG_PATH = LOGS_DIR / "events.jsonl"
ERRORS_LOG_PATH = LOGS_DIR / "errors.jsonl"
COMPLIANCE_LOG_PATH = LOGS_DIR / "compliance.jsonl"

RECORD_INDEX_PATH = INDEXES_DIR / "record_index.json"
MANIFEST_PATH = INDEXES_DIR / "manifest.json"

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Feature flags
# Set ENABLE_EXTERNAL_OUTREACH_LLM=true in .env to allow the outreach module
# to call an external LLM for personalized email drafts.
# When false (default), a safe local template is used instead.
ENABLE_EXTERNAL_OUTREACH_LLM = os.getenv("ENABLE_EXTERNAL_OUTREACH_LLM", "false").lower() == "true"

# Stale-refresh threshold: candidates not updated within this many months
# will be flagged by the auto-refresh job.
STALE_REFRESH_MONTHS = int(os.getenv("STALE_REFRESH_MONTHS", "6"))

# Intake safety limits — prevent DoS via oversized uploads.
# Override via env vars (values in bytes / pages).
MAX_INGEST_FILE_BYTES: int = int(os.getenv("MAX_INGEST_FILE_BYTES", str(5 * 1024 * 1024)))  # 5 MB
MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "25"))


def init_directories():
    directories = [
        RECORDS_DIR,
        REQUIREMENTS_DIR,
        INDEXES_DIR,
        LOGS_DIR,
        POLICIES_DIR,
        QUARANTINE_DIR,
        QUARANTINE_DIR / "schema_failures",
        QUARANTINE_DIR / "parse_failures",
        QUARANTINE_DIR / "security_rejections",
        CVS_DIR,
        LINKEDIN_DIR,
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)

    # Initialize empty indexes if they don't exist
    if not RECORD_INDEX_PATH.exists():
        RECORD_INDEX_PATH.write_text("{}")
    if not MANIFEST_PATH.exists():
        MANIFEST_PATH.write_text("{}")


init_directories()
