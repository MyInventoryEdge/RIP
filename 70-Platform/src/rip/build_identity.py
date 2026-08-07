"""Runtime identity derived from the executable currently running RIP."""
from __future__ import annotations
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.4.0"

def runtime_identity() -> tuple[tuple[str, str, str], ...]:
    executable = Path(sys.executable).resolve()
    try:
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        timestamp = datetime.fromtimestamp(executable.stat().st_mtime, timezone.utc).isoformat()
    except OSError as error:
        return (("Build Identity", "Unavailable", str(error)),)
    return (
        ("Running Executable", "Current", str(executable)),
        ("Version", "Current", VERSION),
        ("Build Timestamp", "Current", timestamp),
        ("Build ID", "Current", digest[:16]),
        ("Executable SHA-256", "Current", digest),
    )
