"""Single-instance file locks for daemons and Telegram long-polling bots.

SQLite is safe for concurrent readers/writers with WAL + busy timeout, but two
*daemon* processes would both consume schedule slots, and two getUpdates
processes on one bot token make Telegram return 409 Conflict.  Both problems are
prevented here with an advisory per-name lock file (``fcntl.flock`` on
macOS/Linux; no lock on platforms without fcntl, so imports stay portable).
"""
from __future__ import annotations

import hashlib
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

try:  # POSIX (macOS/Linux/Docker)
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]


class LockError(RuntimeError):
    """Another process already holds this lock."""


class FileLock:
    """Advisory lock around ``<data_dir>/locks/<name>.lock``."""

    def __init__(self, directory: Path, name: str, *, blocking: bool = False) -> None:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(name))
        self.path = Path(directory) / "locks" / f"{safe}.lock"
        self.blocking = blocking
        self._handle: Optional[object] = None

    def acquire(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a+", encoding="utf-8")
        if fcntl is None:  # pragma: no cover - non-POSIX
            return self
        flags = fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._handle.fileno(), flags)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise LockError(
                f"{self.path.name}: уже запущен другой процесс "
                f"(lock: {self.path})"
            ) from exc
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(f"pid={os.getpid()} host={socket.gethostname()} at={time.time():.0f}\n")
        self._handle.flush()
        return self

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, *args: object) -> None:
        self.release()


@contextmanager
def single_instance(directory: Path | str, name: str, *, blocking: bool = False) -> Iterator[FileLock]:
    """Context manager: raise :class:`LockError` if ``name`` is already held."""
    lock = FileLock(Path(directory), name, blocking=blocking).acquire()
    try:
        yield lock
    finally:
        lock.release()


def telegram_lock_name(token: str) -> str:
    """Stable lock name for one bot token (never store the token itself)."""
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]
    return f"telegram-bot-{digest}"
