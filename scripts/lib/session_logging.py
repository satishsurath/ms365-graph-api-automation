"""Session-level logging for local Microsoft Graph script runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import sys
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


_ACTIVE_SESSION: "SessionLogger | None" = None


@dataclass
class SessionLogger:
    script_name: str
    log_dir: Path
    debug_enabled: bool = False
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    log_path: Path = field(init=False)
    _sequence: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_script_name = self.script_name.replace("/", "-").replace("\\", "-")
        self.log_path = self.log_dir / f"{timestamp}-{safe_script_name}-{self.session_id}.jsonl"

    def log_event(self, event: str, **fields: Any) -> None:
        self._sequence += 1
        record = {
            "timestamp": _utc_now(),
            "sequence": self._sequence,
            "session_id": self.session_id,
            "script_name": self.script_name,
            "event": event,
            **_normalize(fields),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

    def finish(self, *, status: str, **fields: Any) -> None:
        if self._closed:
            return
        self.log_event("session_finished", status=status, **fields)
        self._closed = True


def start_session(
    *,
    script_name: str,
    log_dir: Path,
    debug_enabled: bool = False,
    metadata: dict[str, Any] | None = None,
) -> SessionLogger:
    global _ACTIVE_SESSION

    session = SessionLogger(script_name=script_name, log_dir=log_dir, debug_enabled=debug_enabled)
    session_metadata = dict(metadata or {})
    if debug_enabled:
        session_metadata.update(
            {
                "cwd": Path.cwd(),
                "python_executable": sys.executable,
            }
        )
    _ACTIVE_SESSION = session
    session.log_event(
        "session_started",
        pid=os.getpid(),
        debug_enabled=debug_enabled,
        metadata=session_metadata,
    )
    return session


def get_active_session() -> SessionLogger | None:
    return _ACTIVE_SESSION


def clear_active_session(session: SessionLogger | None = None) -> None:
    global _ACTIVE_SESSION
    if session is None or _ACTIVE_SESSION is session:
        _ACTIVE_SESSION = None
