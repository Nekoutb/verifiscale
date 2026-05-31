"""Object storage abstraction.

In Docker mode this would talk to MinIO; in local/dev mode it writes to the
filesystem under `STORAGE_LOCAL_DIR`. Both expose the same `put_object` /
`get_object` API so callers don't need to care.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings


_settings = get_settings()
_LOCAL_DIR = Path(os.environ.get("STORAGE_LOCAL_DIR", "./_storage")).resolve()


def _local_path(key: str) -> Path:
    return _LOCAL_DIR / key


def ensure_bucket() -> None:
    """Create the local storage directory if missing."""
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)


def put_object(key: str, data: bytes, content_type: str | None = None) -> None:
    ensure_bucket()
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get_object(key: str) -> bytes:
    return _local_path(key).read_bytes()
