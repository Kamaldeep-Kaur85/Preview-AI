"""
tests/unit/test_state_watcher.py

Unit tests for app/state/watcher.py:
- DebounceBuffer coalescing rapid events
- WatchdogFallback polling-based file detection
- create_watcher factory
"""
import time
from pathlib import Path
from app.graph.models import ChangeEvent, ChangeEventType
from app.state.watcher import _DebounceBuffer, WatchdogFallback, create_watcher


def test_debounce_buffer_coalescing():
    emitted = []

    def on_emit(event: ChangeEvent):
        emitted.append(event)

    buf = _DebounceBuffer(on_emit)
    # Temporarily shorten debounce for test speed
    event1 = ChangeEvent(event_type=ChangeEventType.MODIFY, path="/path/to/file.py")
    event2 = ChangeEvent(event_type=ChangeEventType.MODIFY, path="/path/to/file.py")

    buf.push(event1)
    buf.push(event2)

    # Immediately flush
    buf._flush()
    buf.stop()

    assert len(emitted) == 1
    assert emitted[0].path == "/path/to/file.py"


def test_debounce_buffer_rename_priority():
    emitted = []

    def on_emit(event: ChangeEvent):
        emitted.append(event)

    buf = _DebounceBuffer(on_emit)
    rename_ev = ChangeEvent(
        event_type=ChangeEventType.RENAME,
        path="/path/to/new.py",
        old_path="/path/to/old.py",
    )
    mod_ev = ChangeEvent(
        event_type=ChangeEventType.MODIFY,
        path="/path/to/old.py",
    )

    buf.push(rename_ev)
    buf.push(mod_ev)

    buf._flush()
    buf.stop()

    assert len(emitted) == 1
    assert emitted[0].event_type == ChangeEventType.RENAME


def test_watchdog_fallback_diff_and_emit(tmp_path):
    emitted = []

    def on_change(event: ChangeEvent):
        emitted.append(event)

    fallback = WatchdogFallback(root=tmp_path, on_change=on_change)

    f1 = str(tmp_path / "a.py")
    f2 = str(tmp_path / "b.py")

    # 1. Detect CREATE
    before = {}
    after = {f1: 1000.0}
    fallback._diff_and_emit(before, after)
    assert len(emitted) == 1
    assert emitted[0].event_type == ChangeEventType.CREATE
    assert emitted[0].path == f1

    # 2. Detect MODIFY
    emitted.clear()
    before = {f1: 1000.0}
    after = {f1: 1005.0}
    fallback._diff_and_emit(before, after)
    assert len(emitted) == 1
    assert emitted[0].event_type == ChangeEventType.MODIFY

    # 3. Detect DELETE
    emitted.clear()
    before = {f1: 1005.0, f2: 2000.0}
    after = {f2: 2000.0}
    fallback._diff_and_emit(before, after)
    assert len(emitted) == 1
    assert emitted[0].event_type == ChangeEventType.DELETE
    assert emitted[0].path == f1


def test_create_watcher_factory(tmp_path):
    events = []
    watcher = create_watcher(root=tmp_path, on_change=lambda e: events.append(e))
    assert watcher is not None
    assert watcher.root == tmp_path.resolve()
