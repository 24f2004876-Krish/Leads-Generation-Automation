"""
WAT Framework — Tool Utilities
Shared helpers used across tools (env loading, logging, file paths, checkpoints, etc.).
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
TOOLS_DIR = PROJECT_ROOT / "tools"
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"

# Ensure .tmp exists
TMP_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    warnings.warn(
        f".env file not found at {_env_path}. "
        "API keys must be set as environment variables. "
        "See .env.example for required variables.",
        stacklevel=2,
    )


def get_env(key: str, required: bool = True) -> Optional[str]:
    """Retrieve an environment variable, optionally raising if missing."""
    value = os.getenv(key)
    if required and not value:
        raise EnvironmentError(
            f"Missing required env variable: {key}. "
            f"Add it to .env (see .env.example for reference)."
        )
    return value


# ---------------------------------------------------------------------------
# Checkpoint helpers  (shared by app.py and run_pipeline.py)
# ---------------------------------------------------------------------------
CHECKPOINT_SCRAPED = TMP_DIR / "checkpoint_scraped.json"
CHECKPOINT_ENRICHED = TMP_DIR / "checkpoint_enriched.json"


def checkpoints_exist() -> bool:
    """Return True if any checkpoint file is present."""
    return CHECKPOINT_SCRAPED.exists() or CHECKPOINT_ENRICHED.exists()


def clear_checkpoints() -> None:
    """Remove checkpoint files after a successful run."""
    for cp in (CHECKPOINT_SCRAPED, CHECKPOINT_ENRICHED):
        if cp.exists():
            cp.unlink()


def save_checkpoint(path: Path, leads: list, meta: Optional[dict] = None) -> None:
    """Save leads + optional metadata to a JSON checkpoint file."""
    data: dict[str, Any] = {"leads": leads}
    if meta:
        data["meta"] = meta
    path.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def load_checkpoint(path: Path) -> Tuple[Optional[list], Optional[dict]]:
    """Load leads from a checkpoint file. Returns (leads, meta) or (None, None)."""
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("leads"), data.get("meta")
    except (json.JSONDecodeError, KeyError):
        return None, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a user-supplied filename to prevent path traversal.
    Strips directory components, keeping only the base name.
    """
    # Remove any directory traversal / absolute path components
    name = Path(filename).name
    # Remove leading dots (hidden files / traversal)
    name = name.lstrip(".")
    if not name:
        name = "leads.xlsx"
    return name
