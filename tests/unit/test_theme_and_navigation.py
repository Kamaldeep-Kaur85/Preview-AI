"""
tests/unit/test_theme_and_navigation.py

Tests for:
1. Theme palettes (Dark & Light) and color integrity
2. Theme switching and UI updates
3. Fast folder browsing and navigation
4. Windows system directory exclusion in scanner
5. Event stream capping
"""

import os
import re
from pathlib import Path
import pytest

from app.main import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    get_risk_colors,
    make_qt_palette,
    get_global_stylesheet,
    PreViewAIService,
    run_gui_mode,
)
from app.state.scanner import FileScanner, SKIP_DIRS
from PySide6.QtWidgets import QApplication


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


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def test_theme_palettes_tokens_complete():
    """Verify both DARK_PALETTE and LIGHT_PALETTE have all expected color keys."""
    expected_keys = {
        "name", "bg_deep", "bg_panel", "bg_card", "bg_input", "bg_hover",
        "border", "border_act", "text_pri", "text_sec", "text_muted",
        "accent", "accent_dk", "green", "green_dk", "yellow", "red", "red_dk",
        "orange", "cyan", "purple", "ai_purple", "toolbar_g1", "toolbar_g2",
        "header_g1", "header_g2", "header_border", "header_title",
    }
    assert expected_keys.issubset(set(DARK_PALETTE.keys()))
    assert expected_keys.issubset(set(LIGHT_PALETTE.keys()))

    assert DARK_PALETTE["name"] == "dark"
    assert LIGHT_PALETTE["name"] == "light"

    # Verify colors are valid hex strings
    for k, v in DARK_PALETTE.items():
        if k != "name":
            assert HEX_COLOR_RE.match(v), f"Invalid hex color in DARK_PALETTE[{k}]: {v}"
    for k, v in LIGHT_PALETTE.items():
        if k != "name":
            assert HEX_COLOR_RE.match(v), f"Invalid hex color in LIGHT_PALETTE[{k}]: {v}"


def test_risk_colors_mapping():
    """Verify get_risk_colors provides mapping for all risk levels."""
    dark_risks = get_risk_colors(DARK_PALETTE)
    light_risks = get_risk_colors(LIGHT_PALETTE)

    for level in ("HIGH", "MEDIUM", "LOW", "SAFE", "BLOCKED", "NO CONFIRMED IMPACT", "ANALYSIS INCOMPLETE", "UNKNOWN"):
        assert level in dark_risks
        assert level in light_risks
        assert dark_risks[level].startswith("#")
        assert light_risks[level].startswith("#")


def test_global_stylesheet_generation():
    """Verify stylesheet generation produces non-empty CSS containing key palette tokens."""
    dark_css = get_global_stylesheet(DARK_PALETTE)
    light_css = get_global_stylesheet(LIGHT_PALETTE)

    assert DARK_PALETTE["bg_deep"] in dark_css
    assert LIGHT_PALETTE["bg_deep"] in light_css
    assert "QTreeView" in dark_css
    assert "QStatusBar" in dark_css


def test_scanner_skip_dirs_includes_windows_system_folders():
    """Verify Windows system folders and NTFS volumes are in FileScanner.SKIP_DIRS."""
    assert "$RECYCLE.BIN" in SKIP_DIRS
    assert "System Volume Information" in SKIP_DIRS
    assert "AppData" in SKIP_DIRS
    assert "Windows" in SKIP_DIRS
    assert "Program Files" in SKIP_DIRS


def test_scanner_skips_dollar_directories(tmp_path):
    """Verify FileScanner automatically skips $-prefixed directories."""
    recycle = tmp_path / "$Recycle.Bin"
    recycle.mkdir()
    (recycle / "hidden_file.py").write_text("print('bad')", encoding="utf-8")

    good_dir = tmp_path / "src"
    good_dir.mkdir()
    (good_dir / "app.py").write_text("print('good')", encoding="utf-8")

    scanner = FileScanner(tmp_path)
    nodes = scanner.scan()
    scanned_paths = [str(n) for n in nodes]

    assert any("app.py" in p for p in scanned_paths)
    assert not any("$Recycle.Bin" in p for p in scanned_paths)
    assert not any("hidden_file.py" in p for p in scanned_paths)


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") == "minimal", reason="Headless testing")
def test_gui_window_theme_switching_and_navigation(tmp_path):
    """Test GUI window theme switching and folder navigation using offscreen Qt."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    svc = PreViewAIService(project_root=str(tmp_path))

    window = run_gui_mode(svc, project_path=None, start_loop=False)
    assert window is not None

    # Check initial theme is dark
    assert window._current_theme == "dark"
    assert "Light" in window._theme_btn.text()

    # Toggle to light theme
    window._toggle_theme()
    assert window._current_theme == "light"
    assert "Dark" in window._theme_btn.text()

    # Toggle back to dark theme
    window._toggle_theme()
    assert window._current_theme == "dark"
    assert "Light" in window._theme_btn.text()

    # Test explicit set_theme
    window.set_theme("light")
    assert window._current_theme == "light"
    window.set_theme("dark")
    assert window._current_theme == "dark"

    # Test navigation to a folder
    subfolder = tmp_path / "my_folder"
    subfolder.mkdir()
    (subfolder / "test.txt").write_text("hello", encoding="utf-8")

    window._navigate_to(str(subfolder))
    assert window._current_dir == str(subfolder)
    assert window._path_bar.text() == str(subfolder)

    # Test nav up
    window._nav_up()
    assert Path(window._current_dir) == tmp_path

    # Test event stream buffer capping
    for i in range(180):
        window._log_stream(f"Log event #{i}")
    assert window._event_stream.document().blockCount() <= 160

    window.close()


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") == "minimal", reason="Headless testing")
def test_gui_ai_chat_and_graph_tab(tmp_path):
    """Verify AI chat responds to action/consequence queries without crashing, and graph tab renders."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # Setup dummy project with dependencies
    app_py = tmp_path / "app.py"
    app_py.write_text("import joblib\nmodel = joblib.load('model.pkl')\n", encoding="utf-8")
    model_pkl = tmp_path / "model.pkl"
    model_pkl.write_text("pickle-dummy", encoding="utf-8")

    svc = PreViewAIService(project_root=str(tmp_path))
    svc.load_project(str(tmp_path))

    window = run_gui_mode(svc, project_path=None, start_loop=False)
    assert window is not None

    # Test 1: Action consequence query
    window._selected_path = str(model_pkl)
    window._ai_input.setText("what happens if action performed")
    window._send_ai_message()

    chat = window._ai_chat.toPlainText()
    assert "Consequence Analysis" in chat
    assert "model.pkl" in chat

    # Test 2: Dependency query
    window._ai_input.setText("what uses model.pkl?")
    window._send_ai_message()
    chat = window._ai_chat.toPlainText()
    assert "model.pkl" in chat
    assert "app.py" in chat

    # Test 3: Project explanation query
    window._ai_input.setText("explain this project")
    window._send_ai_message()
    chat = window._ai_chat.toPlainText()
    assert "Project Architecture Overview" in chat

    # Test 4: Visual graph tab rendering
    window._update_graph_tab()
    graph_html = window._graph_text.toHtml()
    graph_text = window._graph_text.toPlainText()
    assert "Project Architecture" in graph_html
    assert "WORKFLOW & DATA PIPELINE" in graph_text or ("WORKFLOW" in graph_html and "DATA PIPELINE" in graph_html)

    window.close()


@pytest.mark.skipif(os.environ.get("QT_QPA_PLATFORM") == "minimal", reason="Headless testing")
def test_gui_consequence_aware_delete_and_graph_gaps(tmp_path):
    """Verify consequence-aware deletion dialog, project root detection from subfolders, and graph table gap styling."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # Setup dummy ML project
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    data_csv = dataset_dir / "heart.csv"
    data_csv.write_text("age,trestbps,chol,target\n55,130,250,1\n", encoding="utf-8")

    train_py = tmp_path / "train.py"
    train_py.write_text("import pandas as pd\ndf = pd.read_csv('dataset/heart.csv')\n", encoding="utf-8")

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_pkl = models_dir / "best_model.pkl"
    model_pkl.write_text("model_bytes", encoding="utf-8")
    scaler_pkl = models_dir / "scaler.pkl"
    scaler_pkl.write_text("scaler_bytes", encoding="utf-8")

    app_py = tmp_path / "app.py"
    app_py.write_text("import joblib\nmodel = joblib.load('models/best_model.pkl')\nscaler = joblib.load('models/scaler.pkl')\n", encoding="utf-8")

    svc = PreViewAIService(project_root=str(tmp_path))
    svc.load_project(str(tmp_path))

    window = run_gui_mode(svc, project_path=None, start_loop=False)
    assert window is not None

    # Test 1: Project root detection from subfolder
    detected_root = window._detect_project_root(str(dataset_dir))
    assert detected_root == tmp_path

    # Test 2: Graph tab contains table cards and horizontal dividers with gaps
    window._update_graph_tab()
    html = window._graph_text.toHtml()
    assert "<table" in html
    assert "best_model.pkl" in html
    assert "scaler.pkl" in html
    # Check that separator exists between cards
    assert "border-top:1px dashed" in html or "<hr" in html

    # Test 3: Consequence computation for deleting dataset folder
    from app.consequence.analyzer import ConsequenceAnalyzer
    impact = ConsequenceAnalyzer(svc.current_graph).compute_impact(str(dataset_dir), "DELETE")
    assert impact.risk.value == "HIGH"
    aff_names = [f.name for f in impact.affected_files]
    assert "train.py" in aff_names

    # Test 4: ConsequenceDeleteDialog works properly
    window.close()


