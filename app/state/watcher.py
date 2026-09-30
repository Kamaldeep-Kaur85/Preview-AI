"""
app/state/watcher.py

Real filesystem watcher for the monitored project directory.
Uses watchdog (cross-platform, Windows-compatible) with debouncing.

Events detected:
    CREATE, DELETE, MODIFY, MOVE, RENAME

The watcher runs in a background thread and emits ChangeEvent objects
via a thread-safe callback. It does NOT freeze the UI.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Optional, Set

from app.graph.models import ChangeEvent, ChangeEventType

logger = logging.getLogger("preview_ai.watcher")

# ── Directories and files to ignore ───────────────────────────────────────────
IGNORE_DIRS: Set[str] = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache",
    ".venv", "venv", "env", "node_modules", ".mypy_cache",
    ".eggs", "dist", "build", ".idea", ".vscode",
    ".cache", "cache", "$recycle.bin", "system volume information",
}

IGNORED_EXTENSIONS: Set[str] = {
    ".db", ".db-wal", ".db-shm", ".tmp", ".swp", ".lock",
}

# Debounce window in seconds — coalesce rapid events for the same path
DEBOUNCE_SECONDS = 0.5


class _DebounceBuffer:
    """
    Collects rapid-fire events for the same path and emits a single
    coalesced event after DEBOUNCE_SECONDS of silence.
    """

    def __init__(self, emit_fn: Callable[[ChangeEvent], None]):
        self._emit = emit_fn
        self._pending: Dict[str, ChangeEvent] = {}
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def push(self, event: ChangeEvent):
        with self._lock:
            key = event.old_path or event.path
            # RENAME/MOVE always win over MODIFY for the same path
            existing = self._pending.get(key)
            if existing and existing.event_type in (ChangeEventType.RENAME, ChangeEventType.MOVE):
                pass  # keep the rename
            else:
                self._pending[key] = event

        self._reset_timer()

    def _reset_timer(self):
        if self._timer and self._timer.is_alive():
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE_SECONDS, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self):
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for event in pending:
            try:
                self._emit(event)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")

    def stop(self):
        if self._timer and self._timer.is_alive():
            self._timer.cancel()


class FilesystemWatcher:
    """
    Wraps watchdog to watch a directory and emit ChangeEvent objects.

    Usage:
        watcher = FilesystemWatcher(root=Path("D:/project"), on_change=handler)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(
        self,
        root: Path,
        on_change: Callable[[ChangeEvent], None],
    ):
        self.root = Path(root).resolve()
        self._on_change = on_change
        self._observer = None
        self._debounce = _DebounceBuffer(self._on_change)
        self._running = False

    def start(self) -> bool:
        """Start the filesystem watcher. Returns True if successful."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import (
                FileSystemEventHandler,
                FileCreatedEvent, FileDeletedEvent,
                FileModifiedEvent, FileMovedEvent,
                DirCreatedEvent, DirDeletedEvent,
                DirModifiedEvent, DirMovedEvent,
            )
        except ImportError:
            logger.warning(
                "watchdog not installed. Filesystem monitoring disabled. "
                "Install with: pip install watchdog"
            )
            return False

        watcher_self = self

        class _Handler(FileSystemEventHandler):
            def _should_ignore(self, path_str: str) -> bool:
                p = Path(path_str)
                name_lower = p.name.lower()
                if name_lower.startswith(("state_index.db", ".tmp", "~$")):
                    return True
                if p.suffix.lower() in IGNORED_EXTENSIONS:
                    return True
                for part in p.parts:
                    if part.lower() in IGNORE_DIRS or part.startswith((".", "$")):
                        if part.lower() in IGNORE_DIRS or part in (".cache", ".git", ".venv", "venv", ".idea", ".vscode", "__pycache__", ".pytest_cache", "$recycle.bin"):
                            return True
                return False

            def on_created(self, event):
                if self._should_ignore(event.src_path):
                    return
                watcher_self._debounce.push(ChangeEvent(
                    event_type=ChangeEventType.CREATE,
                    path=str(Path(event.src_path).resolve()),
                    source="USER_MADE",
                ))

            def on_deleted(self, event):
                if self._should_ignore(event.src_path):
                    return
                watcher_self._debounce.push(ChangeEvent(
                    event_type=ChangeEventType.DELETE,
                    path=str(Path(event.src_path).resolve()),
                    source="USER_MADE",
                ))

            def on_modified(self, event):
                if event.is_directory:
                    return
                if self._should_ignore(event.src_path):
                    return
                watcher_self._debounce.push(ChangeEvent(
                    event_type=ChangeEventType.MODIFY,
                    path=str(Path(event.src_path).resolve()),
                    source="USER_MADE",
                ))

            def on_moved(self, event):
                if self._should_ignore(event.src_path):
                    return
                # Distinguish rename (same dir) from move (different dir)
                src = Path(event.src_path).resolve()
                dst = Path(event.dest_path).resolve()
                if src.parent == dst.parent:
                    et = ChangeEventType.RENAME
                else:
                    et = ChangeEventType.MOVE

                watcher_self._debounce.push(ChangeEvent(
                    event_type=et,
                    path=str(dst),
                    old_path=str(src),
                    source="USER_MADE",
                ))

        try:
            self._observer = Observer()
            self._observer.schedule(_Handler(), str(self.root), recursive=True)
            self._observer.start()
            self._running = True
            logger.info(f"Filesystem watcher started on: {self.root}")
            return True
        except Exception as e:
            logger.error(f"Failed to start filesystem watcher: {e}")
            return False

    def stop(self):
        """Stop the filesystem watcher."""
        self._running = False
        self._debounce.stop()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None
        logger.info("Filesystem watcher stopped.")

    @property
    def is_running(self) -> bool:
        return self._running and self._observer is not None


class WatchdogFallback:
    """
    Polling-based fallback when watchdog is not available.
    Polls every N seconds and detects changes by mtime comparison.
    Less efficient but functional without any extra dependencies.
    """

    POLL_INTERVAL = 2.0  # seconds

    def __init__(
        self,
        root: Path,
        on_change: Callable[[ChangeEvent], None],
    ):
        self.root = root.resolve()
        self._on_change = on_change
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._snapshot: Dict[str, float] = {}  # path -> mtime

    def start(self) -> bool:
        self._snapshot = self._take_snapshot()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"Polling watcher started on: {self.root} (interval={self.POLL_INTERVAL}s)")
        return True

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _take_snapshot(self) -> Dict[str, float]:
        snapshot: Dict[str, float] = {}
        for p in self.root.rglob("*"):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue
            try:
                snapshot[str(p)] = p.stat().st_mtime
            except OSError:
                pass
        return snapshot

    def _poll_loop(self):
        while not self._stop_event.wait(self.POLL_INTERVAL):
            try:
                current = self._take_snapshot()
                self._diff_and_emit(self._snapshot, current)
                self._snapshot = current
            except Exception as e:
                logger.error(f"Polling error: {e}")

    def _diff_and_emit(self, before: Dict[str, float], after: Dict[str, float]):
        before_keys = set(before.keys())
        after_keys = set(after.keys())

        for path_str in after_keys - before_keys:
            self._on_change(ChangeEvent(
                event_type=ChangeEventType.CREATE,
                path=path_str,
                source="USER_MADE",
            ))

        for path_str in before_keys - after_keys:
            self._on_change(ChangeEvent(
                event_type=ChangeEventType.DELETE,
                path=path_str,
                source="USER_MADE",
            ))

        for path_str in before_keys & after_keys:
            if before[path_str] != after[path_str]:
                self._on_change(ChangeEvent(
                    event_type=ChangeEventType.MODIFY,
                    path=path_str,
                    source="USER_MADE",
                ))


def create_watcher(
    root: Path,
    on_change: Callable[[ChangeEvent], None],
) -> "FilesystemWatcher | WatchdogFallback":
    """
    Factory: return a FilesystemWatcher (watchdog) if available,
    otherwise return a WatchdogFallback (polling).
    """
    try:
        import watchdog  # noqa: F401
        return FilesystemWatcher(root=root, on_change=on_change)
    except ImportError:
        logger.warning("watchdog not available — using polling fallback")
        return WatchdogFallback(root=root, on_change=on_change)


# Backward-compatible alias
Watcher = FilesystemWatcher

