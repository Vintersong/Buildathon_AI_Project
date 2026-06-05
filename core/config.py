import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from filelock import FileLock

# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RECORDS_DIR = DATA_DIR / "candidates"
REQUIREMENTS_DIR = DATA_DIR / "requirements"
INTAKE_DIR = DATA_DIR / "intake"
QUARANTINE_DIR = DATA_DIR / "quarantine"
LOGS_DIR = DATA_DIR / "logs"

RECORD_INDEX_PATH = DATA_DIR / "record_index.json"
INGEST_MANIFEST_PATH = DATA_DIR / "ingest_manifest.json"
COMPLIANCE_LOG_PATH = LOGS_DIR / "compliance_log.jsonl"
ERROR_LOG_PATH = LOGS_DIR / "error_log.jsonl"
AUDIT_LOG_PATH = LOGS_DIR / "audit_log.jsonl"

# Append-only audit/event feed surfaced by GET /api/audit, plus the error log.
EVENTS_LOG_PATH = LOGS_DIR / "events.jsonl"
ERRORS_LOG_PATH = LOGS_DIR / "errors.jsonl"

# ---------------------------------------------------------------------------
# API key management (.secrets.json — gitignored)
# ---------------------------------------------------------------------------

_SECRETS_PATH = PROJECT_ROOT / ".secrets.json"


def _load_secrets() -> dict:
    try:
        with open(_SECRETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_secrets(data: dict) -> None:
    lock = FileLock(f"{_SECRETS_PATH}.lock")
    with lock:
        # mkstemp creates the file with 0o600 permissions (no world-readable
        # window), then we atomically replace the target path.
        fd, tmp_path = tempfile.mkstemp(dir=_SECRETS_PATH.parent, suffix=".secrets.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            Path(tmp_path).replace(_SECRETS_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# Supported LLM providers and where their keys live.
PROVIDERS = ("gemini", "openai", "anthropic", "huggingface", "local")

_SECRET_KEY_NAMES = {
    "gemini": "gemini_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "huggingface": "huggingface_api_key",
}

_ENV_KEY_NAMES = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
}


def get_provider_api_key(provider: str) -> Optional[str]:
    """Return the active key for ``provider`` (.secrets.json, then env var)."""
    if provider == "local":
        return None  # local servers need no key
    secrets = _load_secrets()
    name = _SECRET_KEY_NAMES.get(provider)
    if name and secrets.get(name):
        return secrets[name]
    env_name = _ENV_KEY_NAMES.get(provider)
    return os.getenv(env_name) if env_name else None


def set_provider_api_key(provider: str, key: Optional[str]) -> None:
    """Persist (or clear) the key for ``provider`` in .secrets.json."""
    name = _SECRET_KEY_NAMES.get(provider)
    if not name:
        return
    secrets = _load_secrets()
    if key:
        secrets[name] = key
    else:
        secrets.pop(name, None)
    _save_secrets(secrets)


def has_provider_api_key(provider: str) -> bool:
    """True when a key for ``provider`` is available (stored or via env)."""
    if provider == "local":
        return False
    secrets = _load_secrets()
    name = _SECRET_KEY_NAMES.get(provider, "")
    if secrets.get(name):
        return True
    env_name = _ENV_KEY_NAMES.get(provider, "")
    return bool(env_name and os.getenv(env_name))


def get_provider_api_key_last4(provider: str) -> Optional[str]:
    key = get_provider_api_key(provider)
    return key[-4:] if key and len(key) >= 4 else None


def get_active_provider() -> str:
    """Return the selected provider from config.json, defaulting to local.

    Honours the legacy ``use_local_llm`` flag when ``provider`` is not set."""
    config_path = PROJECT_ROOT / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    provider = (cfg.get("provider") or "").strip().lower()
    if provider in PROVIDERS:
        return provider
    if cfg.get("use_local_llm"):
        return "local"
    return "local"


def get_active_api_key() -> Optional[str]:
    """Return the user-supplied key from .secrets.json, falling back to the env var.

    Back-compat shim: returns the key for the currently active provider
    (Gemini when none selected)."""
    provider = get_active_provider()
    if provider == "local":
        provider = "gemini"
    return get_provider_api_key(provider)


def get_active_api_key_last4() -> Optional[str]:
    key = get_active_api_key()
    return key[-4:] if key and len(key) >= 4 else None


def has_user_api_key() -> bool:
    """True when a key has been explicitly stored in .secrets.json (not just env var)."""
    secrets = _load_secrets()
    return bool(secrets.get("gemini_api_key"))


def set_active_api_key(key: Optional[str]) -> None:
    """Persist (or clear) the user-supplied Gemini key in .secrets.json."""
    secrets = _load_secrets()
    if key:
        secrets["gemini_api_key"] = key
    else:
        secrets.pop("gemini_api_key", None)
    _save_secrets(secrets)


# ---------------------------------------------------------------------------
# LLM / model configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Override the default model via env var or app config
def get_active_model(default: str) -> str:
    """Return the model name from app config (config.json) if set, else default."""
    config_path = PROJECT_ROOT / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("model") or default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def get_use_local_llm() -> bool:
    config_path = PROJECT_ROOT / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return bool(cfg.get("use_local_llm", False))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def get_confidence_threshold() -> float:
    config_path = PROJECT_ROOT / "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return float(cfg.get("confidence_threshold", 0.85))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.85


# LM Studio local server configuration
def _safe_lm_studio_url(url: str) -> str:
    """Guard against SSRF: only allow localhost/loopback targets."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    _default = "http://localhost:1234/v1"
    if host not in ("localhost", "127.0.0.1", "::1", ""):
        import warnings
        warnings.warn(
            f"LM_STUDIO_BASE_URL {url!r} rejected — must be a localhost address. "
            "Falling back to default.",
            stacklevel=2,
        )
        return _default
    return url

LM_STUDIO_BASE_URL = _safe_lm_studio_url(os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"))
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

# Set ENABLE_EXTERNAL_OUTREACH_LLM=true in .env to allow the outreach module
# to call the configured provider for email drafting. Defaults to false.
ENABLE_EXTERNAL_OUTREACH_LLM = os.getenv("ENABLE_EXTERNAL_OUTREACH_LLM", "false").lower() == "true"

# Feature flag — when False the external LLM call is skipped in extract and match modules
# (safe for air-gapped / no-key deploys). Defaults to true.
ENABLE_EXTERNAL_LLM = os.getenv("ENABLE_EXTERNAL_LLM", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Retention / stale thresholds
# ---------------------------------------------------------------------------

# Number of months before a record is considered stale and eligible for refresh.
STALE_REFRESH_MONTHS = int(os.getenv("STALE_REFRESH_MONTHS", "6"))
