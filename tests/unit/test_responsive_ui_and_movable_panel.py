"""
tests/unit/test_responsive_ui_and_movable_panel.py

Unit tests for:
1. Responsive Explorer Command Bar with Three-Dots ('•••') Overflow:
   - Dynamic button collapsing (text -> icon-only -> '...' menu)
   - Secondary actions in '...' menu (Move to, Copy to, Copy Path, Explorer, Properties)
   - Window width reduction without minimum width blocking
2. Movable and Resizable AI Panel:
   - 6px splitter handle with horizontal resize cursor
   - Panel resizing below 280px down to 150px
   - Detachable / Pop-out floating movable window and smooth docking back
"""

import os
import pytest
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QApplication

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


def test_command_bar_responsive_overflow(tmp_path):
    """Verify that command bar collapses buttons to icon-only and overflows into '...' on narrow widths."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)
    assert window is not None

    cmd_bar = window._cmd_bar
    assert cmd_bar is not None
    assert hasattr(cmd_bar, "_btn_overflow")
    assert hasattr(cmd_bar, "_overflow_menu")

    # 1. Wide mode (>= 720px)
    cmd_bar._update_responsive_layout(800)
    assert window._btn_cut.isVisible()
    assert "Cut" in window._btn_cut.text()
    assert window._btn_copy.isVisible()
    assert "Copy" in window._btn_copy.text()
    assert window._btn_sim_act.isVisible()
    # Overflow menu should have secondary items
    menu_actions = [a.text() for a in cmd_bar._overflow_menu.actions() if a.text()]
    assert any("Move to" in a for a in menu_actions)
    assert any("Copy to" in a for a in menu_actions)
    assert any("Copy Path" in a for a in menu_actions)
    assert any("Windows Explorer" in a for a in menu_actions)

    # 2. Medium mode (480px - 719px): icon-only edit buttons
    cmd_bar._update_responsive_layout(550)
    assert window._btn_cut.isVisible()
    assert window._btn_cut.text() == "✂️"
    assert window._btn_copy.isVisible()
    assert window._btn_copy.text() == "📋"
    assert window._btn_sim_act.isVisible()

    # 3. Compact mode (340px - 479px): Simulate and Delete/Rename overflow into '...'
    cmd_bar._update_responsive_layout(420)
    assert not window._btn_sim_act.isVisible()
    assert not window._btn_delete.isVisible()
    assert not window._btn_rename.isVisible()
    assert window._btn_cut.isVisible()
    # Check that overflow menu now includes Simulate, Delete, Rename
    menu_actions_compact = [a.text() for a in cmd_bar._overflow_menu.actions() if a.text()]
    assert any("Simulate" in a for a in menu_actions_compact)
    assert any("Delete" in a for a in menu_actions_compact)
    assert any("Rename" in a for a in menu_actions_compact)

    # 4. Ultra-compact mode (< 340px): All edit actions overflow into '...'
    cmd_bar._update_responsive_layout(250)
    assert not window._btn_cut.isVisible()
    assert not window._btn_copy.isVisible()
    assert not window._btn_paste.isVisible()
    assert window._btn_overflow.isVisible()
    menu_actions_ultra = [a.text() for a in cmd_bar._overflow_menu.actions() if a.text()]
    assert any("Cut" in a for a in menu_actions_ultra)
    assert any("Copy" in a for a in menu_actions_ultra)
    assert any("Paste" in a for a in menu_actions_ultra)

    window.close()


def test_window_minimum_size_and_splitter_properties(tmp_path):
    """Verify window minimum size allows shrinking, and splitter handles are 6px with resize cursor."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    # Window minimum size must be compact (<= 640x480)
    assert window.minimumWidth() <= 600
    assert window.minimumHeight() <= 450

    # Main splitter must have handleWidth == 6
    assert window._main_splitter.handleWidth() == 6
    assert window._main_splitter.childrenCollapsible() is True

    # Left and right panel minimum widths must allow narrow window sizes
    assert window._left_panel.minimumWidth() <= 120
    assert window._right_stack.minimumWidth() <= 200

    # Splitter handles must have horizontal split cursor
    for i in range(1, 3):
        h = window._main_splitter.handle(i)
        if h:
            assert h.cursor().shape() == Qt.SplitHCursor

    window.close()


def test_ai_panel_popout_and_docking(tmp_path):
    """Verify AI panel can be popped out into a floating movable window and docked back."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    assert hasattr(window, "_ai_popout_btn")
    assert window._ai_popout_btn.text() == "⧉"

    # Open AI panel
    window._ai_btn.setChecked(True)
    window._toggle_ai_panel()
    assert window._right_stack.currentIndex() == 1

    # Pop out AI panel into floating window
    window._toggle_ai_floating()
    assert hasattr(window, "_ai_floating_window")
    assert window._ai_floating_window is not None
    assert window._ai_floating_window.isVisible()
    assert window._ai_page_widget.parent() == window._ai_floating_window
    assert window._ai_popout_btn.text() == "↙"

    # Dock back
    window._toggle_ai_floating()
    assert not window._ai_floating_window.isVisible()
    assert window._ai_page_widget.parent() == window._right_stack
    assert window._ai_popout_btn.text() == "⧉"

    window.close()
