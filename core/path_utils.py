"""Filesystem path guards for ID-addressed JSON records."""
from pathlib import Path


def resolve_json_path(base_dir: Path, item_id: str, *, kind: str = "item") -> Path:
    """Resolve ``<base_dir>/<item_id>.json`` while rejecting traversal IDs."""
    if not item_id or item_id.strip() != item_id:
        raise ValueError(f"Invalid {kind} id: {item_id!r}")
    if "/" in item_id or "\\" in item_id or ".." in item_id:
        raise ValueError(f"Invalid {kind} id: {item_id}")

    base = base_dir.resolve()
    path = (base_dir / f"{item_id}.json").resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"Invalid {kind} id: {item_id}")
    return path
