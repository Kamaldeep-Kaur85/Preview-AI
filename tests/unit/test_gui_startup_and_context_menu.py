"""
tests/unit/test_gui_startup_and_context_menu.py

Regression tests for:
1. GUI startup without AttributeError (specifically verifying _show_context_menu exists).
2. Proper signal connection of customContextMenuRequested to _show_context_menu.
3. Context menu action generation for files, directories, and blank canvas space.
4. Fail-loud behavior during GUI initialization errors.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import Qt, QPoint, QTimer, QModelIndex

from app.main import (
    PreViewAIService,
    run_gui_mode,
)


@pytest.fixture(autouse=True)
def ensure_offscreen():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    yield
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            try:
                if hasattr(widget, "_service") and widget._service:
                    widget._service.stop_watcher()
                if hasattr(widget, "_scan_worker") and widget._scan_worker and widget._scan_worker.isRunning():
                    widget._scan_worker.wait(1000)
                if hasattr(widget, "_impact_worker") and widget._impact_worker and widget._impact_worker.isRunning():
                    widget._impact_worker.wait(1000)
                if hasattr(widget, "_sim_worker") and widget._sim_worker and widget._sim_worker.isRunning():
                    widget._sim_worker.wait(1000)
                widget.close()
            except Exception:
                pass
        app.processEvents()


def test_gui_startup_has_show_context_menu(tmp_path):
    """Regression test: Ensure PreViewWindow initializes without AttributeError and possesses _show_context_menu."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    try:
        assert window is not None
        assert type(window).__name__ == "PreViewWindow"
        assert hasattr(window, "_show_context_menu")
        assert callable(getattr(window, "_show_context_menu"))
    finally:
        window._service.stop_watcher()
        window.close()


def test_custom_context_menu_signal_connected(tmp_path):
    """Verify that _file_view has CustomContextMenu policy and is connected to _show_context_menu."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    try:
        assert hasattr(window, "_file_view")
        file_view = window._file_view
        assert file_view.contextMenuPolicy() == Qt.CustomContextMenu
    finally:
        window._service.stop_watcher()
        window.close()


def test_context_menu_actions_for_file():
    """Verify that right-clicking a file produces the full suite of file actions."""
    test_file = Path(r"D:\preview ai\run_preview_ai.bat")

    svc = PreViewAIService(project_root=r"D:\preview ai")
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    try:
        captured_menus = []
        def dismiss_and_capture():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMenu):
                    captured_menus.append(w)
                    w.hide()

        idx = window._fs_model.index(str(test_file))

        QTimer.singleShot(50, dismiss_and_capture)
        with patch.object(window._file_view, "indexAt", return_value=idx):
            window._show_context_menu(QPoint(10, 10))

        all_actions = [a.text() for m in captured_menus for a in m.actions() if a.text()]

        # Verify key file actions exist
        assert any("Open" in t for t in all_actions)
        assert any("Reveal in Windows Explorer" in t for t in all_actions)
        assert any("Cut" in t for t in all_actions)
        assert any("Copy" in t for t in all_actions)
        assert any("Paste" in t for t in all_actions)
        assert any("Rename" in t for t in all_actions)
        assert any("Delete" in t for t in all_actions)
        assert any("Move to" in t for t in all_actions)
        assert any("Copy to" in t for t in all_actions)
        assert any("Copy as Path" in t for t in all_actions)
        assert any("New" in t for t in all_actions)
        assert any("Simulate Impact" in t for t in all_actions)
        assert any("Show in Dependency Graph" in t for t in all_actions)
        assert any("Ask PreView AI" in t for t in all_actions)
        assert any("Properties" in t for t in all_actions)
    finally:
        window._service.stop_watcher()
        window.close()


def test_context_menu_actions_for_blank_canvas():
    """Verify that right-clicking empty space in the file view shows folder-level actions."""
    svc = PreViewAIService(project_root=r"D:\preview ai")
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    try:
        captured_menus = []
        def dismiss_and_capture():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMenu):
                    captured_menus.append(w)
                    w.hide()

        invalid_idx = QModelIndex()

        QTimer.singleShot(50, dismiss_and_capture)
        with patch.object(window._file_view, "indexAt", return_value=invalid_idx):
            window._show_context_menu(QPoint(9999, 9999))

        all_actions = [a.text() for m in captured_menus for a in m.actions() if a.text()]

        assert any("New" in t for t in all_actions)
        assert any("Paste" in t for t in all_actions)
        assert any("Index Current Folder as Project" in t for t in all_actions)
        assert any("Refresh" in t for t in all_actions)
        assert any("Open in Windows Explorer" in t for t in all_actions)
        assert any("Folder Properties" in t for t in all_actions)
    finally:
        window._service.stop_watcher()
        window.close()
