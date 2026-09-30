"""
tests/unit/test_snapdragon_ai.py

Comprehensive tests for Snapdragon On-Device AI Pipeline:
1. Backend detection:
   - Snapdragon + QNN -> QNN backend (Hexagon NPU)
   - Non-Snapdragon dev machine -> CPU fallback (honest reporting, never faking NPU)
2. Offline operation:
   - Verifies project indexing, dependency analysis, AI inference, and prediction work 100% offline
3. Fast incremental indexing:
   - Verifies single file modification only updates the target file and preserves cached ASTs
4. Prediction accuracy & real performance measurement:
   - Known dependencies (e.g. auth.py -> routes/login.py, database/user.py, tests/test_auth.py)
   - Real measured inference latency (never hardcoded)
5. UI preservation:
   - Verifies existing UI elements remain untouched, AI badge is unobtrusive, and diagnostics trigger correctly
"""

import os
import sys
import time
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.ai.backend import (
    detect_device_info,
    detect_available_providers,
    create_best_backend,
    QNNBackend,
    CPUBackend,
    get_diagnostic_report,
    format_diagnostic_report,
)
from app.ai.context_builder import ProjectContextBuilder
from app.ai.impact_predictor import SnapdragonImpactPredictor
from app.ai.model_manager import ModelManager
from app.graph.builder import GraphBuilder, StateGraph
from app.graph.models import RiskLevel
from app.state.index_cache import IndexCache
from app.main import PreViewAIService, run_gui_mode


@pytest.fixture(autouse=True)
def ensure_offscreen():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Backend Detection Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_backend_detection_on_current_machine():
    """Verify honest backend detection on the current machine."""
    dev_info = detect_device_info()
    assert "device" in dev_info
    assert "machine" in dev_info
    assert "is_snapdragon" in dev_info

    backend = create_best_backend()
    assert backend is not None

    if dev_info["is_snapdragon"] and "QNNExecutionProvider" in detect_available_providers():
        assert isinstance(backend, QNNBackend)
        assert backend.is_npu is True
        assert "Hexagon" in backend.accelerator_name
    else:
        assert isinstance(backend, CPUBackend)
        assert backend.is_npu is False
        assert backend.accelerator_name == "CPU"

    # Verify diagnostic report never claims NPU if running on CPU
    report = get_diagnostic_report(backend)
    assert report["network"] == "Offline"
    if not backend.is_npu:
        assert report["accelerator"] == "CPU"
        assert report["is_npu"] is False


def test_snapdragon_qnn_detection_mocked():
    """Verify that when Snapdragon and QNNExecutionProvider are available, QNNBackend is selected."""
    with patch("app.ai.backend.detect_available_providers", return_value=["QNNExecutionProvider", "CPUExecutionProvider"]):
        with patch("app.ai.backend.detect_device_info", return_value={
            "device": "Snapdragon(R) X Elite - X1E80100 - Qualcomm(R) Oryon(TM) CPU",
            "machine": "ARM64",
            "is_arm64": True,
            "is_snapdragon": True,
            "has_qnn_sdk": True,
            "qnn_libs": ["QnnHtp.dll"],
            "os": "Windows 11",
        }):
            backend = create_best_backend()
            assert isinstance(backend, QNNBackend)
            assert backend.is_npu is True
            assert backend.backend_name == "QNN"
            assert "Hexagon" in backend.accelerator_name


def test_snapdragon_cpu_fallback_mocked():
    """Verify fallback to CPU if on Snapdragon but QNNExecutionProvider is not in ONNX Runtime."""
    with patch("app.ai.backend.detect_available_providers", return_value=["CPUExecutionProvider"]):
        with patch("app.ai.backend.detect_device_info", return_value={
            "device": "Snapdragon(R) X Plus",
            "machine": "ARM64",
            "is_arm64": True,
            "is_snapdragon": True,
            "has_qnn_sdk": False,
            "qnn_libs": [],
            "os": "Windows 11",
        }):
            backend = create_best_backend()
            assert isinstance(backend, CPUBackend)
            assert backend.is_npu is False
            assert backend.accelerator_name == "CPU"


def test_diagnostic_report_format():
    """Verify diagnostic report contains all judging criteria fields."""
    backend = CPUBackend()
    report_text = format_diagnostic_report(backend)

    assert "Hardware" in report_text
    assert "Device:" in report_text
    assert "Architecture:" in report_text
    assert "AI" in report_text
    assert "Runtime: ONNX Runtime" in report_text
    assert "Execution Provider:" in report_text
    assert "Accelerator:" in report_text
    assert "Network: Offline" in report_text
    assert "Performance" in report_text
    assert "Model load:" in report_text
    assert "Inference:" in report_text


# ──────────────────────────────────────────────────────────────────────────────
# 2. Offline-First Verification Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_offline_operation_end_to_end(tmp_path):
    """
    Verify complete project scanning, indexing, AI prediction, and explanation
    operate fully offline with network sockets disabled.
    """
    proj_dir = tmp_path / "offline_project"
    proj_dir.mkdir()
    auth_file = proj_dir / "auth.py"
    auth_file.write_text("def authenticate_user(token):\n    return True\n", encoding="utf-8")
    app_file = proj_dir / "app.py"
    app_file.write_text("import auth\nauth.authenticate_user('test')\n", encoding="utf-8")

    # Simulate network failure on any socket connection attempt
    def blocked_connect(*args, **kwargs):
        raise OSError("Network is unreachable (simulated offline mode)")

    with patch.object(socket.socket, "connect", side_effect=blocked_connect):
        svc = PreViewAIService(project_root=str(proj_dir))
        svc.load_project(str(proj_dir))

        # Graph should be built offline
        assert svc.current_graph is not None
        assert len(svc.current_graph.nodes) >= 2

        # AI prediction should execute offline
        ok, msg, data = svc.simulate_intent("modify auth.py")
        assert ok is True
        assert "impact" in data

        impact = data["impact"]
        assert impact.analysis_complete is True
        assert impact.analysis_time_ms > 0.0

        # Consequence explanation must work offline
        explanation = data["explanation"]
        assert explanation is not None
        assert len(explanation) > 0


# ──────────────────────────────────────────────────────────────────────────────
# 3. Fast Incremental Indexing Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_incremental_indexing_preserves_unrelated_cache(tmp_path):
    """Verify that editing one file only reparses that file and reuses cached ASTs for others."""
    proj_dir = tmp_path / "incremental_project"
    proj_dir.mkdir()

    f1 = proj_dir / "auth.py"
    f1.write_text("def login(): pass\n", encoding="utf-8")

    f2 = proj_dir / "utils.py"
    f2.write_text("def helper(): return 42\n", encoding="utf-8")

    cache_db = proj_dir / ".preview_cache.db"
    cache = IndexCache(cache_db)

    builder = GraphBuilder(proj_dir, cache=cache)
    graph1 = builder.build()

    # Both files must have cached ASTs
    mtime1 = f1.stat().st_mtime
    mtime2 = f2.stat().st_mtime
    assert cache.get_parsed_ast(str(f1), mtime1, f1.stat().st_size) is not None
    assert cache.get_parsed_ast(str(f2), mtime2, f2.stat().st_size) is not None

    # Wait briefly and touch ONLY f1
    time.sleep(0.05)
    f1.write_text("def login(): return 'v2'\ndef logout(): pass\n", encoding="utf-8")
    new_mtime1 = f1.stat().st_mtime

    # Use incremental update on f1
    t0 = time.perf_counter()
    builder.incremental_update_file(graph1, f1, "modified")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Incremental update should complete in sub-50ms (typically sub-5ms)
    assert elapsed_ms < 100.0

    # f1 AST should be updated, and f2 cached AST remains intact and valid
    assert cache.get_parsed_ast(str(f2), mtime2, f2.stat().st_size) is not None
    assert cache.get_parsed_ast(str(f1), new_mtime1, f1.stat().st_size) is not None

    cache.close()


# ──────────────────────────────────────────────────────────────────────────────
# 4. Dependency Prediction & Real Performance Measurement Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_prediction_accuracy_and_latency(tmp_path):
    """
    Verify the AI model predicts the correct dependencies:
    auth.py -> routes/login.py, database/user.py, tests/test_auth.py
    and measures actual, non-hardcoded latency.
    """
    proj_dir = tmp_path / "app_project"
    proj_dir.mkdir()
    routes_dir = proj_dir / "routes"
    routes_dir.mkdir()
    db_dir = proj_dir / "database"
    db_dir.mkdir()
    tests_dir = proj_dir / "tests"
    tests_dir.mkdir()

    auth = proj_dir / "auth.py"
    auth.write_text("class UserAuth:\n    def verify(self): pass\n", encoding="utf-8")

    login = routes_dir / "login.py"
    login.write_text("import auth\ndef login_route():\n    auth.UserAuth().verify()\n", encoding="utf-8")

    user_db = db_dir / "user.py"
    user_db.write_text("import auth\nclass UserModel:\n    pass\n", encoding="utf-8")

    test_auth = tests_dir / "test_auth.py"
    test_auth.write_text("import auth\ndef test_auth(): pass\n", encoding="utf-8")

    builder = GraphBuilder(proj_dir)
    graph = builder.build()

    mm = ModelManager()
    assert mm.is_loaded is True

    t_start = time.perf_counter()
    result = mm.predict_impact(str(auth), "modify", graph)
    t_end = time.perf_counter()

    assert result is not None
    assert result.analysis_complete is True
    # Real measured latency: must be positive and non-zero
    assert result.analysis_time_ms > 0.0
    assert result.inference_time_ms >= 0.0
    # Must NOT be fake hardcoded 42.0 ms
    assert result.analysis_time_ms != 42.0

    # Check affected files contains direct/indirect dependents and tests
    affected_names = [f.name for f in result.all_impacted]
    assert "login.py" in affected_names
    assert "user.py" in affected_names
    assert "test_auth.py" in affected_names

    # Check backend metadata
    assert result.backend_used in ("QNN", "ONNX Runtime")
    assert result.accelerator_used in ("Hexagon NPU", "CPU")


# ──────────────────────────────────────────────────────────────────────────────
# 5. UI Preservation & Diagnostics Dialog Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_ui_preservation_and_components(tmp_path):
    """
    Verify that:
    - Existing file explorer layout, tree, table, and panels are preserved
    - AI panel has subtle hardware badge
    - Diagnostics dialog can be opened without errors
    """
    from PySide6.QtWidgets import QDialog
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)
    assert window is not None

    # Check existing main window structure
    assert hasattr(window, "_left_tree")
    assert hasattr(window, "_right_stack")
    assert hasattr(window, "_ai_page_widget")
    assert hasattr(window, "_preview_info")
    assert hasattr(window, "_preview_impact")
    assert hasattr(window, "_cmd_bar")
    assert hasattr(window, "_status")

    # Check that AI panel header has the subtle Snapdragon/backend badge
    assert hasattr(window, "_ai_status_badge")
    assert window._ai_status_badge is not None
    badge_text = window._ai_status_badge.text()
    assert ("QNN" in badge_text or "ONNX Runtime" in badge_text)

    # Check opening diagnostics dialog
    assert hasattr(window, "_show_ai_diagnostics")
    with patch.object(QDialog, "exec", return_value=QDialog.Accepted):
        window._show_ai_diagnostics()
    window.close()
