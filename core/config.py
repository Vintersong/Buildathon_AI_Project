import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).parent.parent

load_dotenv(BASE_DIR / ".env")

# Local secrets file (gitignored). Keeps user-supplied API keys out of config.json
# (which is committed). On Windows we cannot rely on chmod, so secrecy depends on
# .gitignore + the user's filesystem permissions.
SECRETS_PATH = BASE_DIR / ".secrets.json"

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

# API Keys — env var is the bootstrap default. Runtime overrides live in SECRETS_PATH
# and are read via get_active_api_key() so the UI can rotate keys without a restart.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _load_secrets() -> dict:
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_secrets(data: dict) -> None:
    tmp = SECRETS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(SECRETS_PATH)


def get_active_api_key() -> Optional[str]:
    """Return the runtime-configured Gemini key, falling back to env."""
    key = (_load_secrets().get("gemini_api_key") or "").strip()
    return key or GEMINI_API_KEY


def set_active_api_key(key: Optional[str]) -> None:
    """Persist (or clear) the user-supplied Gemini key. Empty/None clears it."""
    secrets = _load_secrets()
    if key:
        secrets["gemini_api_key"] = key
    else:
        secrets.pop("gemini_api_key", None)
    save_secrets(secrets)


def get_active_api_key_last4() -> Optional[str]:
    key = get_active_api_key()
    if not key or len(key) < 4:
        return None
    return key[-4:]


def has_user_api_key() -> bool:
    """True iff the key came from .secrets.json (not the env fallback)."""
    return bool((_load_secrets().get("gemini_api_key") or "").strip())


# App-config (model name, threshold, etc.) lives in config.json at project root.
# Read directly here so core modules can stay free of any web/* imports.
_APP_CONFIG_PATH = BASE_DIR / "config.json"


def get_active_model(default: str = "gemini-2.5-flash") -> str:
    try:
        with open(_APP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        model = (data.get("model") or "").strip()
        return model or default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def get_use_local_llm() -> bool:
    """When True, extract/match/outreach route through LM Studio on
    http://localhost:1234 instead of Gemini. Set via the Settings UI."""
    try:
        with open(_APP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("use_local_llm", False))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def get_confidence_threshold(default: float = 0.85) -> float:
    try:
        with open(_APP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        value = float(data.get("confidence_threshold", default))
        return min(max(value, 0.0), 1.0)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return default


# LM Studio model identifier sent in the OpenAI-compatible chat request.
# "local-model" is the legacy default; recent LM Studio versions ignore the
# model field when only one is loaded but newer ones require the exact slug.
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "google/gemma-4-e4b")
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")

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
