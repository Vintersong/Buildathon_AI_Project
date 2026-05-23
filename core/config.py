import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

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

# Security/compliance defaults
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
ENABLE_EXTERNAL_LLM = _env_bool("ENABLE_EXTERNAL_LLM", False)
ENABLE_EXTERNAL_OUTREACH_LLM = _env_bool("ENABLE_EXTERNAL_OUTREACH_LLM", False)
ENABLE_LOCAL_EMBEDDINGS = _env_bool("ENABLE_LOCAL_EMBEDDINGS", False)
DEFAULT_RETENTION_DAYS = _env_int("DEFAULT_RETENTION_DAYS", 180)
DEFAULT_DATA_REGION = os.getenv("DEFAULT_DATA_REGION", "EEA")
DEFAULT_CONSENT_BASIS = os.getenv("DEFAULT_CONSENT_BASIS")
TALENT_POOL_ADMIN_TOKEN = os.getenv("TALENT_POOL_ADMIN_TOKEN")
if not TALENT_POOL_ADMIN_TOKEN and APP_ENV in {"development", "local", "test"}:
    TALENT_POOL_ADMIN_TOKEN = "dev-token"

# Intake safety limits
MAX_INGEST_FILE_BYTES = _env_int("MAX_INGEST_FILE_BYTES", 5 * 1024 * 1024)
MAX_PDF_PAGES = _env_int("MAX_PDF_PAGES", 25)

# Create directories if they don't exist
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
