"""Upload handling: validation, safe filenames, persistence."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from core.config import get_settings
from core.exceptions import FileTooLargeError, UnsupportedFileTypeError
from core.logging_config import get_logger

logger = get_logger("files")


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:120] or "upload"


def validate_extension(filename: str, allowed: tuple[str, ...]) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}"
        )
    return ext


def save_upload(content: bytes, filename: str, dest_dir: str, allowed: tuple[str, ...]) -> Path:
    """Validate and persist an uploaded file, returning its path."""
    settings = get_settings()
    validate_extension(filename, allowed)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise FileTooLargeError(f"File exceeds {settings.max_upload_mb} MB limit")
    if not content:
        raise UnsupportedFileTypeError("Uploaded file is empty")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    unique = f"{uuid.uuid4().hex[:8]}_{safe_filename(filename)}"
    path = dest / unique
    path.write_bytes(content)
    logger.info("Saved upload %s (%d bytes)", path, len(content))
    return path
