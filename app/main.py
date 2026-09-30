"""

app/main.py

PreView AI — Local File Explorer + Impact Intelligence System

"See the consequences before your computer acts."

Architecture:

  ┌─────────────────────────────────────────────────────────────┐

  │  TOOLBAR: ← → ↑ ⟳  [path bar]  🔍 Search   ✨ AI          │

  ├──────────────┬──────────────────────────────┬───────────────┤

  │ LEFT PANEL   │   CENTER PANEL               │ RIGHT PANEL   │

  │ File Tree    │   File list / Graph tab       │ Preview /     │

  │ (QTreeView   │   (QFileSystemModel)          │ AI panel      │

  │  QFileSys    │                               │               │

  │  Model)      │                               │               │

  ├──────────────┴──────────────────────────────┴───────────────┤

  │  STATUS BAR: ● Monitor  ● Indexing  Files: N  Relations: N  │

  └─────────────────────────────────────────────────────────────┘

Modes:

  Mode A — AI-proposed action (simulate → approve → execute → verify)

  Mode B — User-made change (watcher → analyze → notify)

"""

from __future__ import annotations

import argparse

import logging

import os

import sys

import time

import threading

from datetime import datetime

from pathlib import Path

from typing import Optional, List, Dict

# Reconfigure stdout/stderr for Unicode support on Windows console

for _s in (sys.stdout, sys.stderr):

    if _s and hasattr(_s, "reconfigure"):

        try:

            _s.reconfigure(encoding="utf-8", errors="replace")

        except Exception:

            pass

# Ensure project root is in sys.path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()

if str(_PROJECT_ROOT) not in sys.path:

    sys.path.insert(0, str(_PROJECT_ROOT))

def _init_logging() -> tuple[logging.Logger, Path]:
    log_dir = None
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            log_dir = Path(local_app_data) / "PreView AI" / "logs"
    if not log_dir:
        log_dir = _PROJECT_ROOT / "logs"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = Path(os.environ.get("TEMP", ".")) / "PreViewAI" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "preview_ai.log"
    
    root_l = logging.getLogger()
    root_l.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if re-imported
    if not any(isinstance(h, logging.FileHandler) for h in root_l.handlers):
        # Console stream handler
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_l.addHandler(sh)
        
        # File handler for GUI/production diagnostics
        try:
            fh = logging.FileHandler(str(log_file), encoding="utf-8", mode="a")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            root_l.addHandler(fh)
        except Exception:
            pass

    l = logging.getLogger("preview_ai")
    l.info(f"PreView AI initializing | Log file: {log_file} | Python {sys.version.split()[0]} | Frozen={getattr(sys, 'frozen', False)}")
    return l, log_file

logger, APPLICATION_LOG_FILE = _init_logging()


def show_fatal_gui_error(title: str, message: str, log_path: Optional[Path] = None):
    """
    Shows a clean GUI message box if a fatal initialization or runtime error occurs,
    ensuring that windowed/no-console builds never fail silently.
    """
    body = message
    if log_path:
        body += f"\n\nDiagnostic log file:\n{log_path}\n\nPlease consult the log file or report this issue."

    # 1. Try PySide6 QMessageBox
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app is None:
            app = QApplication([sys.argv[0]] if sys.argv else ["PreView-AI"])
        QMessageBox.critical(None, title, body)
        return
    except Exception:
        pass

    # 2. Try Windows native MessageBoxW
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, body, title, 0x10)  # 0x10 = MB_ICONERROR
            return
        except Exception:
            pass

    # 3. Fallback to stderr
    if sys.stderr:
        sys.stderr.write(f"\n[FATAL ERROR] {title}: {body}\n")


def _global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled top-level exception", exc_info=(exc_type, exc_value, exc_traceback))
    show_fatal_gui_error(
        "PreView AI — Fatal Error",
        f"An unexpected error occurred:\n\n{exc_value}",
        log_path=APPLICATION_LOG_FILE
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = _global_exception_handler

# Core imports

from app.graph.builder import GraphBuilder, StateGraph

from app.graph.models import (

    StructuredAction, RiskLevel, ConfidenceLevel,

    ImpactResult, ImpactedFile, ChangeEvent, ChangeEventType,

    GraphNode,

)

from app.simulation.simulator import Simulator

from app.consequence.analyzer import ConsequenceAnalyzer

from app.safety.policy import SafetyPolicy

from app.execution.executor import Executor

from app.verification.verifier import Verifier

from app.ai.model_manager import ModelManager

from app.ai.intent_parser import IntentParser

from app.ai.explanation import ExplanationEngine

from app.state.watcher import create_watcher

from app.state.index_cache import IndexCache

# ── D: drive cache path ────────────────────────────────────────────────────

_CACHE_DIR = Path("D:/preview ai/.cache")

_CACHE_DB   = _CACHE_DIR / "state_index.db"

# ══════════════════════════════════════════════════════════════════════════════

# Core Service  (shared between GUI and CLI)

# ══════════════════════════════════════════════════════════════════════════════

class PreViewAIService:

    """Core business logic controller. Thread-safe for background workers."""

    def __init__(self, project_root: Optional[str] = None, cache_path: Optional[Path] = None):

        self.project_root: Path = Path(project_root).resolve() if project_root else Path.cwd()

        self._custom_cache_path = cache_path

        self.model_manager = ModelManager()

        self.intent_parser = IntentParser(self.model_manager)

        self.explanation_engine = ExplanationEngine(self.model_manager)

        self.graph_builder: Optional[GraphBuilder] = None

        self.policy: Optional[SafetyPolicy] = None

        self.current_graph: Optional[StateGraph] = None

        self.last_action: Optional[StructuredAction] = None

        self.last_sim_result = None

        self.last_impact: Optional[ImpactResult] = None

        self.last_explanation: str = ""

        self._watcher = None

        self._on_change_callback = None

        self.event_history: List[tuple] = []

        self._cache: Optional[IndexCache] = None

        self._assistant = None

        self._graph_lock = threading.Lock()

    @property

    def assistant(self):

        if self._assistant is None:

            from app.ai.assistant_router import GlobalAIAssistant

            self._open_cache()

            self._assistant = GlobalAIAssistant(self)

        return self._assistant

    def handle_chat_message(self, message: str):

        """Process chat message through the File Explorer-wide assistant."""

        return self.assistant.process_message(message)

    # ── Cache ──────────────────────────────────────────────────────────────

    def _open_cache(self):

        if self._cache is None:

            try:

                db_p = self._custom_cache_path or _CACHE_DB

                self._cache = IndexCache(db_p)

            except Exception as e:

                logger.warning(f"Cache unavailable: {e}")

    # ── Project load ──────────────────────────────────────────────────────

    def load_project(self, project_root: str) -> bool:

        self.project_root = Path(project_root).resolve()

        self._open_cache()

        self.graph_builder = GraphBuilder(project_root=self.project_root, cache=self._cache)

        self.policy = SafetyPolicy(project_root=self.project_root)

        with self._graph_lock:

            self.current_graph = self.graph_builder.build()

        if self._cache:

            self._cache.set_project_root(str(self.project_root))

        if self._assistant:

            self._assistant.set_navigation_path(str(self.project_root))

            self._assistant.search_engine.cache = self._cache

        # Ensure on-device Snapdragon AI model is loaded and ready

        if self.model_manager and not self.model_manager.is_loaded:

            self.model_manager.load()

        msg = (

            f"Loaded: {self.project_root.name} — "

            f"{self.current_graph.node_count} nodes, "

            f"{self.current_graph.edge_count} edges"

        )

        logger.info(msg)

        self._log_event(msg, None)

        return True

    # ── Watcher ───────────────────────────────────────────────────────────

    def start_watcher(self, on_change) -> bool:

        self.stop_watcher()

        self._on_change_callback = on_change

        if not self.project_root.exists():

            return False

        self._watcher = create_watcher(

            root=self.project_root,

            on_change=self._handle_fs_event,

        )

        return self._watcher.start()

    def stop_watcher(self):

        if self._watcher:

            self._watcher.stop()

            self._watcher = None

    @property

    def watcher_active(self) -> bool:

        return self._watcher is not None and self._watcher.is_running

    def _handle_fs_event(self, event: ChangeEvent):

        # Ignore internal database cache files and system/hidden files

        p = Path(event.path)

        name_lower = p.name.lower()

        if name_lower.startswith(("state_index.db", ".tmp", "~$")) or p.suffix.lower() in (".db", ".db-wal", ".db-shm", ".tmp", ".swp", ".lock"):

            return

        for part in p.parts:

            part_lower = part.lower()

            if part_lower in (".cache", ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "$recycle.bin"):

                return

        logger.info(f"FS event: {event.event_type.value} {event.path}")

        self._update_graph_for_event(event)

        impact = None

        if self.current_graph:

            with self._graph_lock:

                # Run on-device Snapdragon AI model first

                if self.model_manager and self.model_manager.is_loaded:

                    impact = self.model_manager.predict_impact(event.path, event.event_type.value, self.current_graph)

                if not impact:

                    analyzer = ConsequenceAnalyzer(self.current_graph)

                    impact = analyzer.analyze_change_event(event)

            self.last_impact = impact

            path_name = Path(event.path).name

            old_name  = Path(event.old_path).name if event.old_path else None

            desc = (

                f"{event.event_type.value}: {old_name} -> {path_name}"

                if old_name else

                f"{event.event_type.value}: {path_name}"

            )

            self._log_event(desc, impact)

            if self._on_change_callback:

                try:

                    self._on_change_callback(event, impact)

                except Exception as e:

                    logger.error(f"on_change_callback error: {e}")

    def _update_graph_for_event(self, event: ChangeEvent):

        if not self.current_graph or not self.graph_builder:

            return

        try:

            path = Path(event.path)

            with self._graph_lock:

                self.current_graph, _ = self.graph_builder.incremental_update_file(

                    self.current_graph, path, event.event_type.value

                )

        except Exception as e:

            logger.error(f"Incremental graph update failed: {e}")

    # ── Simulation ────────────────────────────────────────────────────────

    def simulate_intent(self, user_intent: str) -> tuple:

        if self.current_graph is None:

            self.load_project(self.project_root)

        action = self.intent_parser.parse(user_intent)

        if not action:

            return False, "Could not parse intent into a structured action. Try: 'rename dataset to dataset_old', 'rename dataset', 'delete dataset', or 'move dataset to backup/'", {}

        self.last_action = action

        if self.policy:

            allowed, reason = self.policy.validate_action(action)

            if not allowed:

                return False, f"Blocked by Safety Policy: {reason}", {"action": action}

        with self._graph_lock:

            graph_snapshot = self.current_graph

        simulator = Simulator(graph_snapshot)

        sim_result  = simulator.simulate(action)

        self.last_sim_result = sim_result

        analyzer = ConsequenceAnalyzer(graph_snapshot)

        analysis = analyzer.analyze(sim_result)

        # Augment with on-device Snapdragon AI prediction

        if self.model_manager and self.model_manager.is_loaded:

            ai_impact = self.model_manager.predict_impact(action.target, action.operation, graph_snapshot)

            if ai_impact and ai_impact.affected_files:

                # Merge validated AI-predicted affected files

                existing_paths = {f.path for f in analysis.impact_result.affected_files}

                for f in ai_impact.affected_files:

                    if f.path not in existing_paths:

                        analysis.impact_result.affected_files.append(f)

                if any(f.risk_level in (RiskLevel.HIGH, RiskLevel.BLOCKED) for f in ai_impact.affected_files):

                    analysis.impact_result.risk = RiskLevel.HIGH

                    analysis.overall_risk = RiskLevel.HIGH

            elif not analysis.impact_result.affected_files:

                # Both deterministic analysis and AI agree: 0 dependent files affected

                analysis.impact_result.risk = RiskLevel.SAFE

                analysis.overall_risk = RiskLevel.SAFE

        self.last_impact  = analysis.impact_result

        explanation       = self.explanation_engine.explain(analysis)

        self.last_explanation = explanation

        self._log_event(f"SIMULATION: {action.operation} {action.target}", analysis.impact_result)

        return True, "OK", {

            "action": action,

            "analysis": analysis,

            "impact": analysis.impact_result,

            "explanation": explanation,

        }

    def get_impact_for_node(self, node_path: str, operation: str = "DELETE") -> Optional[ImpactResult]:

        """Fast impact prediction via Snapdragon on-device AI model with deterministic graph fallback."""

        if not self.current_graph:

            return None

        with self._graph_lock:

            analyzer = ConsequenceAnalyzer(self.current_graph)

            impact = analyzer.compute_impact(node_path, operation)

            if self.model_manager and self.model_manager.is_loaded:

                ai_impact = self.model_manager.predict_impact(node_path, operation, self.current_graph)

                if ai_impact and ai_impact.affected_files:

                    existing_paths = {f.path for f in impact.affected_files}

                    for f in ai_impact.affected_files:

                        if f.path not in existing_paths:

                            impact.affected_files.append(f)

                    if any(f.risk_level in (RiskLevel.HIGH, RiskLevel.BLOCKED) for f in ai_impact.affected_files):

                        impact.risk = RiskLevel.HIGH

                elif not impact.affected_files:

                    impact.risk = RiskLevel.SAFE

            return impact

    @property

    def analyzer(self) -> Optional[ConsequenceAnalyzer]:

        """Convenience property returning a ConsequenceAnalyzer for current_graph."""

        if not self.current_graph:

            return None

        return ConsequenceAnalyzer(self.current_graph)

    @analyzer.setter

    def analyzer(self, val):

        pass

    def execute_and_verify(self) -> tuple:

        if not self.last_action or not self.last_sim_result:

            return False, "No active simulation to execute", {}

        executor = Executor(project_root=self.project_root)

        exec_result = executor.execute(self.last_action)

        exec_ok = exec_result.success

        exec_msg = exec_result.message if exec_ok else exec_result.error

        if not exec_ok:

            self._log_event(f"EXECUTION FAILED: {self.last_action.operation} {self.last_action.target} — {exec_msg}", None)

            return False, f"Execution failed: {exec_msg}", {}

        verifier = Verifier(project_root=self.project_root)

        ver = verifier.verify(self.last_sim_result)

        ver_ok = ver.status in ("MATCH", "PARTIAL_MATCH")

        self._log_event(f"EXECUTED: {self.last_action.operation} {self.last_action.target} (Verification: {ver.status})", None)

        self.load_project(str(self.project_root))

        return ver_ok, exec_msg, {"verification": ver, "diff": exec_result.diff}

    def _log_event(self, desc: str, impact: Optional[ImpactResult]):

        ts = datetime.now().strftime("%H:%M:%S")

        self.event_history.append((ts, desc, impact))

        if len(self.event_history) > 500:

            self.event_history = self.event_history[-500:]

    def get_graph_stats(self) -> dict:

        if not self.current_graph:

            return {"nodes": 0, "edges": 0}

        return {"nodes": self.current_graph.node_count, "edges": self.current_graph.edge_count}

# ── Color systems (Dark & Light) ──────────────────────────────────────

DARK_PALETTE = {

    "name": "dark",

    "bg_deep":     "#0b0d12",

    "bg_panel":    "#111318",

    "bg_card":     "#181c26",

    "bg_input":    "#1c2030",

    "bg_hover":    "#222738",

    "border":      "#252b3d",

    "border_act":  "#3a4a70",

    "text_pri":    "#e2e8f5",

    "text_sec":    "#7a88a8",

    "text_muted":  "#454e68",

    "accent":      "#2563eb",

    "accent_dk":   "#1d4ed8",

    "green":       "#16a34a",

    "green_dk":    "#15803d",

    "yellow":      "#d97706",

    "red":         "#dc2626",

    "red_dk":      "#b91c1c",

    "orange":      "#ea580c",

    "cyan":        "#0891b2",

    "purple":      "#9333ea",

    "ai_purple":   "#7c3aed",

    "toolbar_g1":  "#13161f",

    "toolbar_g2":  "#0b0d12",

    "header_g1":   "#2e1065",

    "header_g2":   "#4c1d95",

    "header_border": "#5b21b6",

    "header_title": "#c4b5fd",

}

LIGHT_PALETTE = {

    "name": "light",

    "bg_deep":     "#f8fafc",     # Slate 50

    "bg_panel":    "#ffffff",     # White

    "bg_card":     "#f1f5f9",     # Slate 100

    "bg_input":    "#ffffff",     # White

    "bg_hover":    "#e2e8f0",     # Slate 200

    "border":      "#cbd5e1",     # Slate 300

    "border_act":  "#94a3b8",     # Slate 400

    "text_pri":    "#0f172a",     # Slate 900

    "text_sec":    "#475569",     # Slate 600

    "text_muted":  "#94a3b8",     # Slate 400

    "accent":      "#4f8ef7",     # Blue 600

    "accent_dk":   "#2a5cc7",     # Blue 700

    "green":       "#22c55e",     # Green 600

    "green_dk":    "#15803d",     # Green 700

    "yellow":      "#f59e0b",     # Amber 600

    "red":         "#ef4444",     # Red 600

    "red_dk":      "#991b1b",     # Red 700

    "orange":      "#f97316",     # Orange 600

    "cyan":        "#06b6d4",     # Cyan 600

    "purple":      "#a855f7",     # Purple 600

    "ai_purple":   "#7c3aed",     # Violet 600

    "toolbar_g1":  "#ffffff",

    "toolbar_g2":  "#f8fafc",

    "header_g1":   "#ede9fe",

    "header_g2":   "#ddd6fe",

    "header_border": "#c4b5fd",

    "header_title": "#5b21b6",

}

def get_risk_colors(colors):

    return {

        "CRITICAL": colors["red"],

        "HIGH": colors["red"], "MEDIUM": colors["yellow"], "LOW": colors["green"],

        "SAFE": colors["green"], "BLOCKED": colors["purple"],

        "NO CONFIRMED IMPACT": colors["green"],

        "ANALYSIS INCOMPLETE": colors["orange"],

        "UNKNOWN": colors["text_muted"],

    }

def make_qt_palette(colors):

    from PySide6.QtGui import QPalette, QColor

    pal = QPalette()

    pal.setColor(QPalette.Window,          QColor(colors["bg_deep"]))

    pal.setColor(QPalette.WindowText,      QColor(colors["text_pri"]))

    pal.setColor(QPalette.Base,            QColor(colors["bg_panel"]))

    pal.setColor(QPalette.AlternateBase,   QColor(colors["bg_card"]))

    pal.setColor(QPalette.Text,            QColor(colors["text_pri"]))

    pal.setColor(QPalette.Button,          QColor(colors["bg_card"]))

    pal.setColor(QPalette.ButtonText,      QColor(colors["text_pri"]))

    pal.setColor(QPalette.Highlight,       QColor(colors["accent"]))

    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    return pal

def get_global_stylesheet(colors):

    return f"""

    * {{ font-family:'Segoe UI','SF Pro Text',sans-serif; font-size:12px; }}

    QMainWindow,QDialog {{ background:{colors['bg_deep']}; }}

    QWidget {{ background:transparent; color:{colors['text_pri']}; }}

    QTreeView,QListView,QListWidget,QTreeWidget {{

        background:{colors['bg_panel']}; border:none;

        color:{colors['text_pri']}; outline:none;

        alternate-background-color:{colors['bg_card']};

    }}

    QTreeView::item,QListWidget::item,QTreeWidget::item {{

        padding:3px 4px; border-radius:3px;

    }}

    QTreeView::item:hover,QListWidget::item:hover,QTreeWidget::item:hover {{

        background:{colors['bg_hover']};

    }}

    QTreeView::item:selected,QListWidget::item:selected,QTreeWidget::item:selected {{

        background:{colors['accent_dk']}; color:#fff;

    }}

    QHeaderView::section {{

        background:{colors['bg_card']}; border:none;

        border-right:1px solid {colors['border']};

        border-bottom:1px solid {colors['border']};

        padding:5px 8px; color:{colors['text_sec']};

        font-size:10px; font-weight:bold; text-transform:uppercase;

        letter-spacing:.5px;

    }}

    QLineEdit {{

        background:{colors['bg_input']}; border:1px solid {colors['border']};

        border-radius:5px; padding:5px 10px;

        color:{colors['text_pri']}; font-size:12px;

    }}

    QLineEdit:focus {{ border-color:{colors['accent']}; }}

    QPushButton {{

        background:{colors['bg_card']}; border:1px solid {colors['border']};

        border-radius:5px; padding:5px 14px;

        color:{colors['text_pri']}; font-size:11px; font-weight:600;

    }}

    QPushButton:hover {{ background:{colors['bg_hover']}; border-color:{colors['border_act']}; }}

    QPushButton:pressed {{ background:{colors['bg_input']}; }}

    QPushButton:disabled {{ color:{colors['text_muted']}; }}

    QToolButton {{

        background:transparent; border:none;

        color:{colors['text_sec']}; padding:4px 8px; font-size:11px;

    }}

    QToolButton:hover {{ background:{colors['bg_hover']}; border-radius:4px; color:{colors['text_pri']}; }}

    QTextEdit {{

        background:{colors['bg_panel']}; border:none;

        color:{colors['text_pri']}; font-size:12px; padding:6px;

    }}

    QSplitter::handle {{ background:{colors['border']}; }}

    QSplitter::handle:horizontal {{

        background: {colors['border']};

        width: 6px;

    }}

    QSplitter::handle:horizontal:hover {{

        background: {colors['accent']};

    }}

    QSplitter::handle:horizontal:pressed {{

        background: {colors['accent_dk']};

    }}

    QScrollBar:vertical {{ background:{colors['bg_panel']}; width:5px; }}

    QScrollBar::handle:vertical {{ background:{colors['border_act']}; border-radius:2px; min-height:20px; }}

    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }}

    QScrollBar:horizontal {{ background:{colors['bg_panel']}; height:5px; }}

    QScrollBar::handle:horizontal {{ background:{colors['border_act']}; border-radius:2px; }}

    QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {{ width:0; }}

    QStatusBar {{ background:{colors['bg_deep']}; color:{colors['text_sec']}; font-size:10px; border-top:1px solid {colors['border']}; }}

    QMenu {{ background:{colors['bg_card']}; border:1px solid {colors['border']}; color:{colors['text_pri']}; padding:4px 0; }}

    QMenu::item {{ padding:5px 24px 5px 12px; }}

    QMenu::item:selected {{ background:{colors['accent_dk']}; color:#fff; }}

    QMenu::separator {{ height:1px; background:{colors['border']}; margin:3px 0; }}

    QTabWidget::pane {{ border-top:1px solid {colors['border']}; }}

    QTabBar::tab {{ background:{colors['bg_card']}; border:1px solid {colors['border']};

        border-bottom:none; padding:5px 14px; color:{colors['text_sec']}; font-size:11px; }}

    QTabBar::tab:selected {{ background:{colors['bg_panel']}; color:{colors['text_pri']};

        border-bottom:2px solid {colors['accent']}; }}

    QProgressBar {{ border:none; background:{colors['bg_input']}; height:2px; border-radius:1px; }}

    QProgressBar::chunk {{ background:{colors['accent']}; }}

    """

# ══════════════════════════════════════════════════════════════════════════════

# GUI

# ══════════════════════════════════════════════════════════════════════════════

def run_gui_mode(service: PreViewAIService, project_path: Optional[str] = None, start_loop: bool = True):

    from PySide6.QtWidgets import (

        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,

        QLabel, QLineEdit, QPushButton, QTextEdit, QPlainTextEdit, QTextBrowser, QFileDialog, QDialog,

        QTreeView, QListWidget, QListWidgetItem, QMessageBox, QGroupBox,

        QSplitter, QFrame, QScrollArea, QSizePolicy, QStatusBar,

        QTabWidget, QHeaderView, QAbstractItemView, QToolButton,

        QStackedWidget, QMenu, QProgressBar, QToolBar, QStyle,

        QFileSystemModel, QTreeWidget, QTreeWidgetItem, QInputDialog,

    )

    from PySide6.QtCore import (

        Qt, QThread, Signal, QTimer, QSize, QDir, QModelIndex,

        QObject, Slot, QRunnable, QThreadPool, QSortFilterProxyModel,

        QFileInfo, QPoint, QUrl, QMimeData,

    )

    from PySide6.QtGui import (

        QFont, QColor, QPalette, QAction, QIcon, QCursor, QTextCursor,

        QStandardItemModel, QStandardItem, QShortcut, QKeySequence, QDrag,

    )

    app = QApplication.instance() or QApplication(sys.argv)

    app.setStyle("Fusion")

    C = dict(DARK_PALETTE)

    RISK_C = get_risk_colors(C)

    app.setPalette(make_qt_palette(C))

    app.setStyleSheet(get_global_stylesheet(C))

    # ── Worker classes ────────────────────────────────────────────────────

    class ScanWorker(QThread):

        progress    = Signal(str)

        finished    = Signal(bool, str)

        def __init__(self, svc, path):

            super().__init__(); self.svc = svc; self.path = path

        def run(self):

            try:

                self.progress.emit(f"Scanning {self.path}...")

                self.svc.load_project(self.path)

                self.finished.emit(True, "OK")

            except Exception as e:

                self.finished.emit(False, str(e))

    class SimWorker(QThread):

        finished = Signal(bool, str, object)

        def __init__(self, svc, intent):

            super().__init__(); self.svc = svc; self.intent = intent

        def run(self):

            try:

                ok, msg, data = self.svc.simulate_intent(self.intent)

                self.finished.emit(ok, msg, data)

            except Exception as e:

                self.finished.emit(False, str(e), {})

    class ImpactWorker(QThread):

        finished = Signal(object)  # ImpactResult or None

        def __init__(self, svc, node_path, operation="DELETE"):

            super().__init__()

            self.svc = svc; self.node_path = node_path; self.operation = operation

        def run(self):

            try:

                result = self.svc.get_impact_for_node(self.node_path, self.operation)

                self.finished.emit(result)

            except Exception:

                self.finished.emit(None)

    # ════════════════════════════════════════════════════════════════════════

    # Consequence Delete Dialog

    # ════════════════════════════════════════════════════════════════════════

    class ConsequenceDeleteDialog(QDialog):

        """

        AI Consequence-Aware Deletion Dialog.

        Computes real risk level, detects contained files if folder,

        and presents dependent project files that will be broken.

        """

        def __init__(self, parent, path_str: str, impact: Optional[ImpactResult], colors: dict, risk_colors: dict):

            super().__init__(parent)

            self.setModal(True)

            self.setWindowTitle("PreView AI — Consequence Aware Delete")

            self.resize(640, 520)

            self.p = Path(path_str)

            self.path_str = path_str

            self.impact = impact

            self.C = colors

            self.RISK_C = risk_colors

            self.action_choice = "CANCEL"

            self._build_ui()

        def _build_ui(self):

            self.setStyleSheet(f"background: {self.C['bg_deep']};")

            layout = QVBoxLayout(self)

            layout.setContentsMargins(20, 20, 20, 20)

            layout.setSpacing(14)

            # Header row: icon + title

            hdr_layout = QHBoxLayout()

            is_high_risk = self.impact and (self.impact.risk in (RiskLevel.HIGH, RiskLevel.BLOCKED))

            icon_lbl = QLabel("⚠️" if is_high_risk else "🗑️")

            icon_lbl.setStyleSheet("font-size: 32px;")

            hdr_layout.addWidget(icon_lbl)

            info_layout = QVBoxLayout()

            title_lbl = QLabel(f"Delete '{self.p.name}'?")

            title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {self.C['text_pri']};")

            info_layout.addWidget(title_lbl)

            kind = "Folder" if self.p.is_dir() else "File"

            sub_lbl = QLabel(f"Type: {kind}  •  Path: {self.path_str}")

            sub_lbl.setStyleSheet(f"font-size: 11px; color: {self.C['text_sec']};")

            info_layout.addWidget(sub_lbl)

            hdr_layout.addLayout(info_layout, stretch=1)

            layout.addLayout(hdr_layout)

            # Risk Banner

            risk_val = self.impact.risk.value if self.impact else "UNKNOWN"

            risk_color = self.RISK_C.get(risk_val, self.C['accent'])

            risk_banner = QLabel(f"⚡ IMPACT ASSESSMENT:  {risk_val} RISK")

            risk_banner.setStyleSheet(f"""

                background: {risk_color}; color: #ffffff; font-weight: 800;

                font-size: 11px; padding: 6px 12px; border-radius: 5px;

                letter-spacing: 0.5px;

            """)

            layout.addWidget(risk_banner)

            # Details text area

            details_view = QTextEdit()

            details_view.setReadOnly(True)

            details_view.setStyleSheet(f"""

                QTextEdit {{

                    background: {self.C['bg_deep']};

                    border: 1px solid {self.C['border']};

                    border-radius: 6px;

                    color: {self.C['text_pri']};

                    font-size: 11px;

                    padding: 8px;

                }}

            """)

            html_body = f"<div style='font-family:Segoe UI,sans-serif; color:{self.C['text_pri']};'>"

            # If folder, show folder contents

            if self.p.is_dir():

                try:

                    children = list(self.p.iterdir())

                    html_body += f"<div style='margin-bottom:10px; color:{self.C['text_sec']};'>"

                    html_body += f"📁 <b>Folder Contents</b>: Contains <b>{len(children)}</b> item(s) on disk."

                    if children:

                        items_str = ", ".join(f"<code>{c.name}</code>" for c in children[:8])

                        if len(children) > 8:

                            items_str += f", and {len(children) - 8} more…"

                        html_body += f"<br><span style='color:{self.C['text_muted']}; font-size:10px;'>({items_str})</span>"

                    html_body += "</div>"

                except Exception:

                    pass

            # Affected files table

            aff_files = self.impact.affected_files if self.impact else []

            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['yellow']}; margin-bottom:8px; font-size:12px;'>

                  ⚠️ {len(env_deps)} Environment Dependenc{'ies' if len(env_deps) != 1 else 'y'} detected:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']}; margin-bottom:12px;'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>VARIABLE & SOURCE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CATEGORY</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['red']}; margin-bottom:8px; font-size:12px;'>

                  🚨 {len(aff_files)} project file{'s' if len(aff_files) != 1 else ''} depend on this component and will BREAK:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']};'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>AFFECTED FILE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>RELATIONSHIP</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CONSEQUENCE & WHY</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style='padding:12px; color:{self.C['green']}; font-weight:bold; font-size:12px;'>

                  ✓ No dependent project files or environment references found. It appears safe to remove.

                </div>

                """

            html_body += "</div>"

            details_view.setHtml(html_body)

            layout.addWidget(details_view, stretch=1)

            # Buttons row

            btn_row = QHBoxLayout()

            btn_cancel = QPushButton("❌  Cancel")

            btn_cancel.setDefault(True)

            btn_cancel.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['border']};

                    color: {self.C['text_pri']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['bg_hover']};

                }}

            """)

            btn_cancel.clicked.connect(self._on_cancel)

            btn_row.addWidget(btn_cancel)

            btn_sim = QPushButton("⚡  Open in Simulator")

            btn_sim.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['accent']};

                    color: {self.C['accent']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['accent_dk']};

                    color: #ffffff;

                }}

            """)

            btn_sim.clicked.connect(self._on_simulate)

            btn_row.addWidget(btn_sim)

            btn_row.addStretch()

            is_dangerous = self.impact and (self.impact.risk in (RiskLevel.HIGH, RiskLevel.BLOCKED) or len(aff_files) > 0)

            del_text = "🗑  I Understand Risk — Delete" if is_dangerous else "🗑  Move to Recycle Bin"

            btn_del = QPushButton(del_text)

            if is_dangerous:

                btn_del.setStyleSheet("""

                    QPushButton {

                        background: #b91c1c;

                        border: 1px solid #ef4444;

                        color: #ffffff;

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }

                    QPushButton:hover {

                        background: #ef4444;

                    }

                """)

            else:

                btn_del.setStyleSheet(f"""

                    QPushButton {{

                        background: {self.C['bg_card']};

                        border: 1px solid {self.C['border']};

                        color: {self.C['red']};

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }}

                    QPushButton:hover {{

                        border-color: {self.C['red']};

                    }}

                """)

            btn_del.clicked.connect(self._on_delete)

            btn_row.addWidget(btn_del)

            layout.addLayout(btn_row)

        def _on_cancel(self):

            self.action_choice = "CANCEL"

            self.reject()

        def _on_simulate(self):

            self.action_choice = "SIMULATE"

            self.accept()

        def _on_delete(self):

            self.action_choice = "DELETE"

            self.accept()

    # ════════════════════════════════════════════════════════════════════════

    # Consequence Move Dialog

    # ════════════════════════════════════════════════════════════════════════

    class ConsequenceMoveDialog(QDialog):

        """

        AI Consequence-Aware Move Confirmation Dialog.

        Displays broken dependents when moving files or folders across directories.

        """

        def __init__(self, parent, src_path: str, dest_path: str, impact: Optional[ImpactResult], colors: dict, risk_colors: dict):

            super().__init__(parent)

            self.setModal(True)

            self.setWindowTitle("PreView AI — Consequence Aware Move")

            self.resize(640, 520)

            self.src = Path(src_path)

            self.dest = Path(dest_path)

            self.impact = impact

            self.C = colors

            self.RISK_C = risk_colors

            self.action_choice = "CANCEL"

            self._build_ui()

        def _build_ui(self):

            self.setStyleSheet(f"background: {self.C['bg_deep']};")

            layout = QVBoxLayout(self)

            layout.setContentsMargins(20, 20, 20, 20)

            layout.setSpacing(14)

            # Header row: icon + title

            hdr_layout = QHBoxLayout()

            is_high_risk = self.impact and (self.impact.risk in (RiskLevel.HIGH, RiskLevel.BLOCKED))

            icon_lbl = QLabel("⚠️" if is_high_risk else "📦")

            icon_lbl.setStyleSheet("font-size: 32px;")

            hdr_layout.addWidget(icon_lbl)

            info_layout = QVBoxLayout()

            title_lbl = QLabel(f"Move '{self.src.name}'?")

            title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {self.C['text_pri']};")

            info_layout.addWidget(title_lbl)

            kind = "Folder" if self.src.is_dir() else "File"

            sub_lbl = QLabel(f"Type: {kind}  •  Destination: {self.dest.parent.name}/")

            sub_lbl.setStyleSheet(f"font-size: 11px; color: {self.C['text_sec']};")

            info_layout.addWidget(sub_lbl)

            hdr_layout.addLayout(info_layout, stretch=1)

            layout.addLayout(hdr_layout)

            # Risk Banner

            risk_val = self.impact.risk.value if self.impact else "UNKNOWN"

            risk_color = self.RISK_C.get(risk_val, self.C['accent'])

            risk_banner = QLabel(f"⚡ IMPACT ASSESSMENT:  {risk_val} RISK")

            risk_banner.setStyleSheet(f"""

                background: {risk_color}; color: #ffffff; font-weight: 800;

                font-size: 11px; padding: 6px 12px; border-radius: 5px;

                letter-spacing: 0.5px;

            """)

            layout.addWidget(risk_banner)

            # Details text area

            details_view = QTextEdit()

            details_view.setReadOnly(True)

            details_view.setStyleSheet(f"""

                QTextEdit {{

                    background: {self.C['bg_deep']};

                    border: 1px solid {self.C['border']};

                    border-radius: 6px;

                    color: {self.C['text_pri']};

                    font-size: 11px;

                    padding: 8px;

                }}

            """)

            html_body = f"<div style='font-family:Segoe UI,sans-serif; color:{self.C['text_pri']};'>"

            html_body += f"<div style='margin-bottom:10px; color:{self.C['text_sec']};'>"

            html_body += f"📦 <b>Moving from:</b> <code>{self.src}</code><br>➔ <b>Moving to:</b> <code>{self.dest}</code>"

            html_body += "</div>"

            aff_files = self.impact.affected_files if self.impact else []

            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['yellow']}; margin-bottom:8px; font-size:12px;'>

                  ⚠️ {len(env_deps)} Environment Dependenc{'ies' if len(env_deps) != 1 else 'y'} detected:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']}; margin-bottom:12px;'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>VARIABLE & SOURCE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CATEGORY</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['red']}; margin-bottom:8px; font-size:12px;'>

                  🚨 {len(aff_files)} project file{'s' if len(aff_files) != 1 else ''} depend on this component at its current location and will BREAK:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']};'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>AFFECTED FILE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>RELATIONSHIP</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style='padding:12px; color:{self.C['green']}; font-weight:bold; font-size:12px;'>

                  ✓ No broken references detected. It appears safe to move.

                </div>

                """

            html_body += "</div>"

            details_view.setHtml(html_body)

            layout.addWidget(details_view, stretch=1)

            # Buttons row

            btn_row = QHBoxLayout()

            btn_cancel = QPushButton("❌  Cancel")

            btn_cancel.setDefault(True)

            btn_cancel.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['border']};

                    color: {self.C['text_pri']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['bg_hover']};

                }}

            """)

            btn_cancel.clicked.connect(self._on_cancel)

            btn_row.addWidget(btn_cancel)

            btn_sim = QPushButton("⚡  Open in Simulator")

            btn_sim.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['accent']};

                    color: {self.C['accent']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['accent_dk']};

                    color: #ffffff;

                }}

            """)

            btn_sim.clicked.connect(self._on_simulate)

            btn_row.addWidget(btn_sim)

            btn_row.addStretch()

            is_dangerous = self.impact and (self.impact.risk in (RiskLevel.HIGH, RiskLevel.BLOCKED) or len(aff_files) > 0)

            move_text = "📦  I Understand Risk — Move" if is_dangerous else "📦  Move"

            btn_move = QPushButton(move_text)

            if is_dangerous:

                btn_move.setStyleSheet("""

                    QPushButton {

                        background: #b45309;

                        border: 1px solid #f59e0b;

                        color: #ffffff;

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }

                    QPushButton:hover {

                        background: #d97706;

                    }

                """)

            else:

                btn_move.setStyleSheet(f"""

                    QPushButton {{

                        background: {self.C['bg_card']};

                        border: 1px solid {self.C['border']};

                        color: {self.C['accent']};

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }}

                    QPushButton:hover {{

                        border-color: {self.C['accent']};

                    }}

                """)

            btn_move.clicked.connect(self._on_move)

            btn_row.addWidget(btn_move)

            layout.addLayout(btn_row)

        def _on_cancel(self):

            self.action_choice = "CANCEL"

            self.reject()

        def _on_simulate(self):

            self.action_choice = "SIMULATE"

            self.accept()

        def _on_move(self):

            self.action_choice = "MOVE"

            self.accept()

    # ════════════════════════════════════════════════════════════════════════

    # Consequence Rename Dialog

    # ════════════════════════════════════════════════════════════════════════

    class ConsequenceRenameDialog(QDialog):

        """

        AI Consequence-Aware Rename Confirmation Dialog.

        Displays which files will be affected and broken if a component is renamed,

        allows user to enter the new name, and offers OK (Rename) or Cancel.

        """

        def __init__(self, parent, src_path: str, impact: Optional[ImpactResult], colors: dict, risk_colors: dict):

            super().__init__(parent)

            self.setModal(True)

            self.setWindowTitle("PreView AI — Consequence Aware Rename")

            self.resize(640, 540)

            self.src = Path(src_path)

            self.impact = impact

            self.C = colors

            self.RISK_C = risk_colors

            self.action_choice = "CANCEL"

            self.new_name = self.src.name

            self._build_ui()

        def _build_ui(self):

            self.setStyleSheet(f"background: {self.C['bg_deep']};")

            layout = QVBoxLayout(self)

            layout.setContentsMargins(18, 18, 18, 18)

            layout.setSpacing(12)

            aff_files = self.impact.affected_files if self.impact else []

            is_dangerous = self.impact and (self.impact.risk in (RiskLevel.HIGH, RiskLevel.BLOCKED) or len(aff_files) > 0)

            risk_color = self.RISK_C.get(self.impact.risk if self.impact else RiskLevel.LOW, "#10b981")

            # Header Banner

            header_frame = QFrame()

            header_frame.setStyleSheet(f"""

                QFrame {{

                    background: {self.C['bg_card']};

                    border: 1px solid {risk_color if is_dangerous else self.C['border']};

                    border-radius: 8px;

                    padding: 10px 14px;

                }}

            """)

            h_layout = QHBoxLayout(header_frame)

            h_layout.setContentsMargins(0, 0, 0, 0)

            h_layout.setSpacing(12)

            icon_lbl = QLabel("✏️")

            icon_lbl.setStyleSheet("font-size: 26px;")

            h_layout.addWidget(icon_lbl)

            info_layout = QVBoxLayout()

            info_layout.setSpacing(3)

            title_text = "Rename Component — Consequence Analysis"

            title_lbl = QLabel(title_text)

            title_lbl.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {self.C['text_pri']};")

            info_layout.addWidget(title_lbl)

            if is_dangerous:

                sub_text = f"⚠️ Renaming will BREAK references in {len(aff_files)} project file{'s' if len(aff_files) != 1 else ''}!"

                sub_col = self.C['red']

            else:

                sub_text = "✓ Safe to rename — No incoming dependencies will be broken."

                sub_col = self.C['green']

            sub_lbl = QLabel(sub_text)

            sub_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {sub_col};")

            info_layout.addWidget(sub_lbl)

            h_layout.addLayout(info_layout, stretch=1)

            layout.addWidget(header_frame)

            # Name Input Card

            input_card = QFrame()

            input_card.setStyleSheet(f"""

                QFrame {{

                    background: {self.C['bg_deep']};

                    border: 1px solid {self.C['border']};

                    border-radius: 6px;

                    padding: 10px;

                }}

            """)

            ic_layout = QVBoxLayout(input_card)

            ic_layout.setContentsMargins(6, 6, 6, 6)

            ic_layout.setSpacing(8)

            curr_lbl = QLabel(f"Current Name:  <b>{self.src.name}</b>  <span style='color:{self.C['text_muted']}; font-size:10px;'>({self.src})</span>")

            curr_lbl.setStyleSheet(f"color: {self.C['text_pri']}; font-size: 11px;")

            ic_layout.addWidget(curr_lbl)

            inp_row = QHBoxLayout()

            new_lbl = QLabel("New Name:")

            new_lbl.setStyleSheet(f"font-weight: 600; color: {self.C['text_pri']}; font-size: 11px;")

            inp_row.addWidget(new_lbl)

            self.name_edit = QLineEdit(self.src.name)

            self.name_edit.setStyleSheet(f"""

                QLineEdit {{

                    background: {self.C['bg_panel']};

                    border: 1px solid {self.C['accent']};

                    border-radius: 4px;

                    color: {self.C['text_pri']};

                    padding: 5px 8px;

                    font-size: 12px;

                    font-weight: 600;

                }}

            """)

            # Select stem by default

            stem_len = len(self.src.stem)

            self.name_edit.setSelection(0, stem_len)

            self.name_edit.textChanged.connect(self._on_text_changed)

            self.name_edit.returnPressed.connect(self._on_rename)

            inp_row.addWidget(self.name_edit, stretch=1)

            ic_layout.addLayout(inp_row)

            self.err_lbl = QLabel("")

            self.err_lbl.setStyleSheet(f"color: {self.C['red']}; font-size: 10px; font-weight: 600;")

            self.err_lbl.setVisible(False)

            ic_layout.addWidget(self.err_lbl)

            layout.addWidget(input_card)

            # Details / Affected files view

            details_view = QTextEdit()

            details_view.setReadOnly(True)

            details_view.setStyleSheet(f"""

                QTextEdit {{

                    background: {self.C['bg_deep']};

                    border: 1px solid {self.C['border']};

                    border-radius: 6px;

                    color: {self.C['text_pri']};

                    font-size: 11px;

                    padding: 8px;

                }}

            """)

            html_body = f"<div style='font-family:Segoe UI,sans-serif; color:{self.C['text_pri']};'>"

            env_deps = getattr(self.impact, "environment_dependencies", []) if self.impact else []

            if env_deps:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['yellow']}; margin-bottom:8px; font-size:12px;'>

                  ⚠️ {len(env_deps)} Environment Dependenc{'ies' if len(env_deps) != 1 else 'y'} detected:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']}; margin-bottom:12px;'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>VARIABLE & SOURCE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CATEGORY</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>EVIDENCE & WHY IT MATTERS</th>

                  </tr>

                """

                for f in env_deps:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            if aff_files:

                html_body += f"""

                <div style='font-weight:700; color:{self.C['red']}; margin-bottom:8px; font-size:12px;'>

                  🚨 {len(aff_files)} project file{'s' if len(aff_files) != 1 else ''} depend on '{self.src.name}' and will break if renamed:

                </div>

                <table width='100%' cellpadding='6' cellspacing='0' style='border-collapse:collapse; border:1px solid {self.C['border']};'>

                  <tr style='background:{self.C['bg_card']}; font-size:10px; font-weight:bold; color:{self.C['text_muted']};'>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>AFFECTED FILE</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>RELATIONSHIP</th>

                    <th align='left' style='padding:5px 8px; border-bottom:1px solid {self.C['border']};'>CONSEQUENCE</th>

                  </tr>

                """

                for f in aff_files:

                    html_body += f"""

                    <tr style='border-bottom:1px solid {self.C['border']}; font-size:11px;'>

                      <td style='padding:6px 8px; color:{self.C['yellow']}; font-weight:bold;'>{f.name}</td>

                      <td style='padding:6px 8px; color:{self.C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:6px 8px; color:{self.C['text_pri']}; font-size:10px;'>{f.description or f.evidence_summary}</td>

                    </tr>

                    """

                html_body += "</table>"

            elif not env_deps:

                html_body += f"""

                <div style='padding:12px; color:{self.C['green']}; font-weight:bold; font-size:12px;'>

                  ✓ No dependent files found in this project. It is safe to rename '{self.src.name}'.

                </div>

                """

            html_body += "</div>"

            details_view.setHtml(html_body)

            layout.addWidget(details_view, stretch=1)

            # Buttons row

            btn_row = QHBoxLayout()

            btn_cancel = QPushButton("❌  Cancel")

            btn_cancel.setDefault(True)

            btn_cancel.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['border']};

                    color: {self.C['text_pri']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['bg_hover']};

                }}

            """)

            btn_cancel.clicked.connect(self._on_cancel)

            btn_row.addWidget(btn_cancel)

            btn_sim = QPushButton("⚡  Open in Simulator")

            btn_sim.setStyleSheet(f"""

                QPushButton {{

                    background: {self.C['bg_card']};

                    border: 1px solid {self.C['accent']};

                    color: {self.C['accent']};

                    font-weight: 600;

                    padding: 8px 18px;

                    border-radius: 5px;

                }}

                QPushButton:hover {{

                    background: {self.C['accent_dk']};

                    color: #ffffff;

                }}

            """)

            btn_sim.clicked.connect(self._on_simulate)

            btn_row.addWidget(btn_sim)

            btn_row.addStretch()

            ren_text = "✏️  I Understand Risk — Rename" if is_dangerous else "✏️  Rename"

            self.btn_rename = QPushButton(ren_text)

            if is_dangerous:

                self.btn_rename.setStyleSheet("""

                    QPushButton {

                        background: #b45309;

                        border: 1px solid #f59e0b;

                        color: #ffffff;

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }

                    QPushButton:hover {

                        background: #d97706;

                    }

                    QPushButton:disabled {

                        background: #555;

                        border-color: #666;

                        color: #888;

                    }

                """)

            else:

                self.btn_rename.setStyleSheet(f"""

                    QPushButton {{

                        background: {self.C['bg_card']};

                        border: 1px solid {self.C['border']};

                        color: {self.C['accent']};

                        font-weight: 700;

                        padding: 8px 18px;

                        border-radius: 5px;

                    }}

                    QPushButton:hover {{

                        border-color: {self.C['accent']};

                    }}

                    QPushButton:disabled {{

                        color: {self.C['text_muted']};

                        border-color: {self.C['border']};

                    }}

                """)

            self.btn_rename.clicked.connect(self._on_rename)

            self.btn_rename.setEnabled(False)

            btn_row.addWidget(self.btn_rename)

            layout.addLayout(btn_row)

            # Trigger initial validation state

            self._on_text_changed(self.name_edit.text())

        def _on_text_changed(self, text: str):

            val = text.strip()

            if not val or val == self.src.name:

                self.btn_rename.setEnabled(False)

                self.err_lbl.setVisible(False)

                return

            invalid_chars = set(r'\/:*?"<>|')

            if any(c in invalid_chars for c in val):

                self.err_lbl.setText("Name cannot contain: \\ / : * ? \" < > |")

                self.err_lbl.setVisible(True)

                self.btn_rename.setEnabled(False)

                return

            target = self.src.parent / val

            if target.exists():

                self.err_lbl.setText(f"An item named '{val}' already exists.")

                self.err_lbl.setVisible(True)

                self.btn_rename.setEnabled(False)

                return

            self.err_lbl.setVisible(False)

            self.btn_rename.setEnabled(True)

        def _on_cancel(self):

            self.action_choice = "CANCEL"

            self.reject()

        def _on_simulate(self):

            val = self.name_edit.text().strip()

            self.new_name = val if val else self.src.name

            self.action_choice = "SIMULATE"

            self.accept()

        def _on_rename(self):

            val = self.name_edit.text().strip()

            if not val or val == self.src.name:

                return

            invalid_chars = set(r'\/:*?"<>|')

            if any(c in invalid_chars for c in val):

                return

            target = self.src.parent / val

            if target.exists():

                return

            self.new_name = val

            self.action_choice = "RENAME"

            self.accept()

    # ════════════════════════════════════════════════════════════════════════

    # Windows 11 File Explorer Command Bar with Three-Dots ('•••') Overflow

    # ════════════════════════════════════════════════════════════════════════

    class ResponsiveExplorerCommandBar(QWidget):

        """

        Windows 11 File Explorer Command Bar with responsive overflow.

        Dynamically collapses buttons to icon-only and three dots ('•••' / See more)

        as window width shrinks, preventing minimum width constraints and mimicking

        the exact responsive behavior of Windows 11 File Explorer.

        """

        def __init__(self, win: "PreViewWindow"):

            super().__init__()

            self._win = win

            self.setFixedHeight(38)

            self.setMinimumWidth(80)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            self._init_ui()

        def _init_ui(self):

            layout = QHBoxLayout(self)

            layout.setContentsMargins(6, 2, 6, 2)

            layout.setSpacing(4)

            # 1. New Dropdown Button

            self._btn_new = QToolButton(self)

            self._btn_new.setText("➕ New ▾")

            self._btn_new.setPopupMode(QToolButton.InstantPopup)

            new_menu = QMenu(self._btn_new)

            act_nfolder = QAction("📁  Folder\tCtrl+Shift+N", new_menu)

            act_nfolder.triggered.connect(lambda: self._win._new_folder())

            new_menu.addAction(act_nfolder)

            act_nfile = QAction("📄  Text Document", new_menu)

            act_nfile.triggered.connect(lambda: self._win._new_file("New Document.txt"))

            new_menu.addAction(act_nfile)

            act_npy = QAction("🐍  Python Script", new_menu)

            act_npy.triggered.connect(lambda: self._win._new_file("script.py"))

            new_menu.addAction(act_npy)

            act_ncfg = QAction("⚙️  Config File (.json)", new_menu)

            act_ncfg.triggered.connect(lambda: self._win._new_file("config.json"))

            new_menu.addAction(act_ncfg)

            self._btn_new.setMenu(new_menu)

            layout.addWidget(self._btn_new)

            # Separator 1

            self._sep1 = QFrame(self)

            self._sep1.setFrameShape(QFrame.VLine)

            layout.addWidget(self._sep1)

            # 2. Cut Button

            self._btn_cut = QToolButton(self)

            self._btn_cut.setText("✂️ Cut")

            self._btn_cut.setToolTip("Cut selection (Ctrl+X)")

            self._btn_cut.clicked.connect(lambda: self._win._cut_selection())

            layout.addWidget(self._btn_cut)

            # 3. Copy Button

            self._btn_copy = QToolButton(self)

            self._btn_copy.setText("📋 Copy")

            self._btn_copy.setToolTip("Copy selection (Ctrl+C)")

            self._btn_copy.clicked.connect(lambda: self._win._copy_selection())

            layout.addWidget(self._btn_copy)

            # 4. Paste Button

            self._btn_paste = QToolButton(self)

            self._btn_paste.setText("📥 Paste")

            self._btn_paste.setToolTip("Paste from clipboard (Ctrl+V)")

            self._btn_paste.setEnabled(False)

            self._btn_paste.clicked.connect(lambda: self._win._paste_selection())

            layout.addWidget(self._btn_paste)

            # 5. Rename Button

            self._btn_rename = QToolButton(self)

            self._btn_rename.setText("✏️ Rename")

            self._btn_rename.setToolTip("Rename selection (F2)")

            self._btn_rename.clicked.connect(lambda: self._win._rename_file())

            layout.addWidget(self._btn_rename)

            # 6. Delete Button

            self._btn_delete = QToolButton(self)

            self._btn_delete.setText("🗑️ Delete")

            self._btn_delete.setToolTip("Consequence-Aware Delete (Del)")

            self._btn_delete.clicked.connect(lambda: self._win._delete_file())

            layout.addWidget(self._btn_delete)

            # Separator 2

            self._sep2 = QFrame(self)

            self._sep2.setFrameShape(QFrame.VLine)

            layout.addWidget(self._sep2)

            # 7. Simulate Impact Button (highlighted)

            self._btn_sim_act = QPushButton("⚡ Simulate", self)

            self._btn_sim_act.setToolTip("Simulate what happens if selected file/folder is created, deleted, modified, moved, or renamed")

            self._btn_sim_act.clicked.connect(lambda: self._win._simulate_selected_item())

            layout.addWidget(self._btn_sim_act)

            layout.addStretch()

            # 8. Three Dots ('•••' / See more) Button

            self._btn_overflow = QToolButton(self)

            self._btn_overflow.setText("•••")

            self._btn_overflow.setToolTip("See more options")

            self._btn_overflow.setPopupMode(QToolButton.InstantPopup)

            self._overflow_menu = QMenu(self._btn_overflow)

            self._btn_overflow.setMenu(self._overflow_menu)

            layout.addWidget(self._btn_overflow)

            # Overflow Actions

            self._act_sim_act = QAction("⚡  Simulate Selection", self)

            self._act_sim_act.triggered.connect(lambda: self._win._simulate_selected_item())

            self._act_delete = QAction("🗑️  Delete\tDel", self)

            self._act_delete.triggered.connect(lambda: self._win._delete_file())

            self._act_rename = QAction("✏️  Rename\tF2", self)

            self._act_rename.triggered.connect(lambda: self._win._rename_file())

            self._act_paste = QAction("📥  Paste\tCtrl+V", self)

            self._act_paste.triggered.connect(lambda: self._win._paste_selection())

            self._act_copy = QAction("📋  Copy\tCtrl+C", self)

            self._act_copy.triggered.connect(lambda: self._win._copy_selection())

            self._act_cut = QAction("✂️  Cut\tCtrl+X", self)

            self._act_cut.triggered.connect(lambda: self._win._cut_selection())

            self._overflow_sep1 = QAction(self)

            self._overflow_sep1.setSeparator(True)

            self._act_moveto = QAction("📦  Move to…", self)

            self._act_moveto.triggered.connect(lambda: self._win._move_to_dialog())

            self._act_copyto = QAction("📂  Copy to…", self)

            self._act_copyto.triggered.connect(lambda: self._win._copy_to_dialog())

            self._act_copypath = QAction("🔗  Copy Path\tCtrl+Shift+C", self)

            self._act_copypath.triggered.connect(lambda: self._win._copy_as_path())

            self._act_os_exp = QAction("🪟  Open in Windows Explorer", self)

            self._act_os_exp.triggered.connect(lambda: self._win._reveal_in_os_explorer())

            self._overflow_sep2 = QAction(self)

            self._overflow_sep2.setSeparator(True)

            self._act_properties = QAction("ℹ️  Properties\tAlt+Enter", self)

            self._act_properties.triggered.connect(lambda: self._win._show_properties(self._win._get_active_selected_path()))

            # Attach attributes to window

            self._win._btn_new = self._btn_new

            self._win._btn_cut = self._btn_cut

            self._win._btn_copy = self._btn_copy

            self._win._btn_paste = self._btn_paste

            self._win._btn_rename = self._btn_rename

            self._win._btn_delete = self._btn_delete

            self._win._btn_sim_act = self._btn_sim_act

            self._win._btn_overflow = self._btn_overflow

            self._win._act_moveto = self._act_moveto

            self._win._act_copyto = self._act_copyto

            self._win._act_copypath = self._act_copypath

            self._win._act_os_exp = self._act_os_exp

            self._win._act_sim_act = self._act_sim_act

            self._win._act_delete = self._act_delete

            self._win._act_rename = self._act_rename

            self._win._act_paste = self._act_paste

            self._win._act_copy = self._act_copy

            self._win._act_cut = self._act_cut

            self._win._btn_moveto = self._act_moveto

            self._win._btn_copyto = self._act_copyto

            self._win._btn_copypath = self._act_copypath

            self._win._btn_os_exp = self._act_os_exp

            self._apply_theme()

            self._update_responsive_layout(self.width())

        def _apply_theme(self):

            self.setStyleSheet(f"""

                QWidget {{

                    background: {self._win.C['bg_panel']};

                    border-bottom: 1px solid {self._win.C['border']};

                }}

                QToolButton, QPushButton {{

                    background: transparent;

                    border: 1px solid transparent;

                    border-radius: 4px;

                    color: {self._win.C['text_pri']};

                    font-size: 11px;

                    padding: 3px 6px;

                    font-weight: 500;

                }}

                QToolButton:hover, QPushButton:hover {{

                    background: {self._win.C['bg_hover']};

                    border-color: {self._win.C['border']};

                }}

                QToolButton:pressed, QPushButton:pressed {{

                    background: {self._win.C['accent_dk']};

                }}

                QToolButton:disabled, QPushButton:disabled {{

                    color: {self._win.C['text_muted']};

                    border-color: transparent;

                }}

                QMenu {{

                    background: {self._win.C['bg_card']};

                    border: 1px solid {self._win.C['border']};

                    padding: 4px;

                }}

                QMenu::item {{

                    padding: 6px 20px;

                    color: {self._win.C['text_pri']};

                    border-radius: 3px;

                }}

                QMenu::item:selected {{

                    background: {self._win.C['accent']};

                    color: #ffffff;

                }}

                QMenu::separator {{

                    height: 1px;

                    background: {self._win.C['border']};

                    margin: 4px 0;

                }}

            """)

            if hasattr(self, "_sep1"):

                self._sep1.setStyleSheet(f"color: {self._win.C['border']};")

            if hasattr(self, "_sep2"):

                self._sep2.setStyleSheet(f"color: {self._win.C['border']};")

            if hasattr(self, "_btn_sim_act"):

                self._btn_sim_act.setStyleSheet(f"""

                    QPushButton {{

                        background: {self._win.C['bg_card']};

                        border: 1px solid {self._win.C['accent']};

                        color: {self._win.C['accent']};

                        font-weight: 600;

                        border-radius: 4px;

                        padding: 3px 10px;

                    }}

                    QPushButton:hover {{

                        background: {self._win.C['accent_dk']};

                        color: #fff;

                    }}

                """)

            if hasattr(self, "_btn_overflow"):

                self._btn_overflow.setStyleSheet(f"""

                    QToolButton {{

                        font-size: 13px;

                        font-weight: bold;

                        letter-spacing: 1px;

                        padding: 2px 8px;

                        color: {self._win.C['text_pri']};

                    }}

                    QToolButton::menu-indicator {{ image: none; width: 0px; }}

                """)

        def resizeEvent(self, event):

            super().resizeEvent(event)

            self._update_responsive_layout(self.width())

        def _update_responsive_layout(self, w: int):

            self._overflow_menu.clear()

            if w >= 720:

                self._btn_cut.setText("✂️ Cut")

                self._btn_copy.setText("📋 Copy")

                self._btn_paste.setText("📥 Paste")

                self._btn_rename.setText("✏️ Rename")

                self._btn_delete.setText("🗑️ Delete")

                self._btn_sim_act.setText("⚡ Simulate")

                self._btn_new.setText("➕ New ▾")

                self._btn_cut.setVisible(True)

                self._btn_copy.setVisible(True)

                self._btn_paste.setVisible(True)

                self._btn_rename.setVisible(True)

                self._btn_delete.setVisible(True)

                self._btn_sim_act.setVisible(True)

                self._sep1.setVisible(True)

                self._sep2.setVisible(True)

            elif w >= 480:

                # Windows 11 File Explorer style: icons for standard edit actions

                self._btn_cut.setText("✂️")

                self._btn_copy.setText("📋")

                self._btn_paste.setText("📥")

                self._btn_rename.setText("✏️")

                self._btn_delete.setText("🗑️")

                self._btn_sim_act.setText("⚡ Simulate")

                self._btn_new.setText("➕ New ▾")

                self._btn_cut.setVisible(True)

                self._btn_copy.setVisible(True)

                self._btn_paste.setVisible(True)

                self._btn_rename.setVisible(True)

                self._btn_delete.setVisible(True)

                self._btn_sim_act.setVisible(True)

                self._sep1.setVisible(True)

                self._sep2.setVisible(True)

            elif w >= 340:

                # Moderate width: overflow Simulate and Delete/Rename into '...'

                self._btn_cut.setText("✂️")

                self._btn_copy.setText("📋")

                self._btn_paste.setText("📥")

                self._btn_new.setText("➕ New ▾")

                self._btn_cut.setVisible(True)

                self._btn_copy.setVisible(True)

                self._btn_paste.setVisible(True)

                self._btn_rename.setVisible(False)

                self._btn_delete.setVisible(False)

                self._btn_sim_act.setVisible(False)

                self._sep1.setVisible(True)

                self._sep2.setVisible(False)

                self._overflow_menu.addAction(self._act_sim_act)

                self._overflow_menu.addAction(self._act_rename)

                self._overflow_menu.addAction(self._act_delete)

                self._overflow_menu.addAction(self._overflow_sep1)

            else:

                # Ultra-compact (< 340): All edit actions overflow into '...'

                self._btn_new.setText("➕")

                self._btn_cut.setVisible(False)

                self._btn_copy.setVisible(False)

                self._btn_paste.setVisible(False)

                self._btn_rename.setVisible(False)

                self._btn_delete.setVisible(False)

                self._btn_sim_act.setVisible(False)

                self._sep1.setVisible(False)

                self._sep2.setVisible(False)

                self._overflow_menu.addAction(self._act_sim_act)

                self._overflow_menu.addAction(self._act_cut)

                self._overflow_menu.addAction(self._act_copy)

                self._overflow_menu.addAction(self._act_paste)

                self._overflow_menu.addAction(self._act_rename)

                self._overflow_menu.addAction(self._act_delete)

                self._overflow_menu.addAction(self._overflow_sep1)

            # Standard items always present in '...'

            self._overflow_menu.addAction(self._act_moveto)

            self._overflow_menu.addAction(self._act_copyto)

            self._overflow_menu.addAction(self._act_copypath)

            self._overflow_menu.addAction(self._act_os_exp)

            self._overflow_menu.addAction(self._overflow_sep2)

            self._overflow_menu.addAction(self._act_properties)

        def update_action_state(self, has_sel: bool, has_clip: bool):

            self._btn_cut.setEnabled(has_sel)

            self._btn_copy.setEnabled(has_sel)

            self._btn_rename.setEnabled(has_sel)

            self._btn_delete.setEnabled(has_sel)

            self._btn_sim_act.setEnabled(has_sel)

            self._btn_paste.setEnabled(has_clip)

            self._act_cut.setEnabled(has_sel)

            self._act_copy.setEnabled(has_sel)

            self._act_rename.setEnabled(has_sel)

            self._act_delete.setEnabled(has_sel)

            self._act_sim_act.setEnabled(has_sel)

            self._act_paste.setEnabled(has_clip)

            self._act_moveto.setEnabled(has_sel)

            self._act_copyto.setEnabled(has_sel)

            self._act_copypath.setEnabled(has_sel)

            self._act_properties.setEnabled(has_sel or bool(self._win._current_dir))

    # ════════════════════════════════════════════════════════════════════════

    # Main Window

    # ════════════════════════════════════════════════════════════════════════

    class ChatInputEdit(QPlainTextEdit):
        """Custom multiline chat input: Enter to submit, Shift+Enter for newline."""
        def __init__(self, on_submit, parent=None):
            super().__init__(parent)
            self._on_submit = on_submit
            self.setPlaceholderText("Ask PreView AI... (Enter to send, Shift+Enter for newline)")

        def text(self) -> str:
            return self.toPlainText()

        def setText(self, val: str):
            self.setPlainText(val)

        def keyPressEvent(self, event):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    super().keyPressEvent(event)
                else:
                    event.accept()
                    if self._on_submit:
                        self._on_submit()
            else:
                super().keyPressEvent(event)

    class PreViewWindow(QMainWindow):

        fs_change_signal = Signal(object, object)

        impact_ready     = Signal(object)

        def __init__(self):

            super().__init__()

            self.setWindowTitle("PreView AI — File Intelligence & Consequence Awareness")

            self.resize(1440, 900)

            self.setMinimumSize(540, 400)

            self._service       = service

            self._current_theme = "dark"

            self.C              = C

            self.RISK_C         = RISK_C

            self._scan_worker   = None

            self._sim_worker    = None

            self._impact_worker = None

            self._ai_open       = False

            self._selected_path: Optional[str] = None

            self._current_impact: Optional[ImpactResult] = None

            self._impact_cache: Dict[str, ImpactResult] = {}

            self._search_scope = "PROJECT"

            self._user_approved_locations: List[Path] = []

            self._operation_history: List[Dict[str, Any]] = []

            # Track files with impact indicators {path: state}

            self._impact_states: Dict[str, str] = {}

            self._current_dir: Optional[str] = None

            self._clipboard_path: Optional[str] = None

            self._clipboard_mode: Optional[str] = None  # "CUT" or "COPY"

            self.ConsequenceDeleteDialog = ConsequenceDeleteDialog

            self.ConsequenceMoveDialog = ConsequenceMoveDialog

            self.ConsequenceRenameDialog = ConsequenceRenameDialog

            self.fs_change_signal.connect(self._on_fs_change_ui)

            self.impact_ready.connect(self._on_impact_ready)

            self._build_ui()

            self._update_action_bar_state()

            try:

                QApplication.clipboard().dataChanged.connect(self._update_action_bar_state)

            except Exception:

                pass

            # Global Shortcuts

            from PySide6.QtGui import QKeySequence, QShortcut

            QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._open_folder_dialog)

            QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self._toggle_theme)

            if project_path:

                self._navigate_to(project_path)

                if not (hasattr(self, "_scan_worker") and self._scan_worker is not None and self._scan_worker.isRunning()):

                    self._start_scan(project_path)

            else:

                init_path = str(_PROJECT_ROOT)

                self._navigate_to(init_path)

        # ── Theme Management ──────────────────────────────────────────────

        def set_theme(self, theme_name: str):

            """Dynamically switch between Dark Mode and Light Mode."""

            theme_name = theme_name.lower().strip()

            palette = LIGHT_PALETTE if theme_name == "light" else DARK_PALETTE

            self._current_theme = "light" if theme_name == "light" else "dark"

            C.clear()

            C.update(palette)

            self.C = C

            RISK_C.clear()

            RISK_C.update(get_risk_colors(C))

            self.RISK_C = RISK_C

            # Apply global application palette & stylesheet

            app.setPalette(make_qt_palette(self.C))

            app.setStyleSheet(get_global_stylesheet(self.C))

            # Update Toolbar

            if hasattr(self, "_toolbar"):

                self._toolbar.setStyleSheet(f"""

                    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,

                        stop:0 {self.C['toolbar_g1']}, stop:1 {self.C['toolbar_g2']});

                    border-bottom:1px solid {self.C['border']};

                """)

            if hasattr(self, "_theme_btn"):

                self._theme_btn.setText("☀️  Light" if self._current_theme == "dark" else "🌙  Dark")

                self._theme_btn.setToolTip("Switch to Light mode (Ctrl+T)" if self._current_theme == "dark" else "Switch to Dark mode (Ctrl+T)")

            # Update Left Panel

            if hasattr(self, "_left_panel"):

                self._left_panel.setStyleSheet(f"background:{self.C['bg_panel']}; border-right:1px solid {self.C['border']};")

            if hasattr(self, "_left_header"):

                self._left_header.setStyleSheet(f"""

                    background:{self.C['bg_card']}; color:{self.C['text_muted']};

                    font-size:9px; font-weight:bold; letter-spacing:1px;

                    padding:0 10px; border-bottom:1px solid {self.C['border']};

                """)

            if hasattr(self, "_left_tree"):

                self._populate_left_tree()

            # Update Center Panel

            if hasattr(self, "_center_widget"):

                self._center_widget.setStyleSheet(f"background:{self.C['bg_deep']};")

            if hasattr(self, "_addr_bar"):

                self._addr_bar.setStyleSheet(f"background:{self.C['bg_card']}; border-bottom:1px solid {self.C['border']};")

                self._addr_label.setStyleSheet(f"color:{self.C['text_sec']}; font-size:11px;")

                if self._current_dir:

                    self._update_index_badge(self._current_dir)

            if hasattr(self, "_center_tabs"):

                self._center_tabs.setStyleSheet(f"""

                    QTabWidget::pane {{ border:none; border-top:1px solid {self.C['border']}; }}

                    QTabBar::tab {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};

                        border-bottom:none; padding:5px 14px; color:{self.C['text_sec']}; font-size:11px; }}

                    QTabBar::tab:selected {{ background:{self.C['bg_panel']}; color:{self.C['accent']};

                        border-bottom:2px solid {self.C['accent']}; }}

                """)

            if hasattr(self, "_file_view"):

                self._file_view.setStyleSheet(f"""

                    QTreeView {{ background:{self.C['bg_panel']}; border:none; }}

                    QTreeView::item {{ padding:4px 6px; }}

                    QTreeView::item:hover {{ background:{self.C['bg_hover']}; }}

                    QTreeView::item:selected {{ background:{self.C['accent_dk']}; color:#fff; }}

                """)

            if hasattr(self, "_graph_text"):

                self._graph_text.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_panel']}; border:1px solid {self.C['border']};

                        border-radius:6px; font-family:'Cascadia Code','Consolas',monospace;

                        font-size:11px; color:{self.C['text_pri']}; padding:10px; }}

                """)

            if hasattr(self, "_sim_result"):

                self._sim_result.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_panel']}; border:1px solid {self.C['border']};

                        border-radius:6px; color:{self.C['text_pri']}; font-size:12px; padding:10px; }}

                """)

            # Update Right Panel

            if hasattr(self, "_right_stack"):

                self._right_stack.setStyleSheet(f"background:{self.C['bg_panel']}; border-left:1px solid {self.C['border']};")

            if hasattr(self, "_preview_info"):

                self._preview_info.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_card']}; border:none; border-bottom:1px solid {self.C['border']};

                        color:{self.C['text_sec']}; font-size:11px; padding:10px; }}

                """)

            if hasattr(self, "_preview_impact"):

                self._preview_impact.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_panel']}; border:none;

                        color:{self.C['text_sec']}; font-size:11px; padding:10px; line-height:1.7; }}

                """)

            if hasattr(self, "_qa_bar"):

                self._qa_bar.setStyleSheet(f"background:{self.C['bg_card']}; border-top:1px solid {self.C['border']};")

            if hasattr(self, "_ai_ctx"):

                self._ai_ctx.setStyleSheet(f"""

                    background:{self.C['bg_card']}; color:{self.C['text_muted']};

                    font-size:10px; padding:0 12px;

                    border-bottom:1px solid {self.C['border']};

                """)

            if hasattr(self, "_ai_chat"):

                self._ai_chat.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_deep']}; border:none;

                        color:{self.C['text_pri']}; font-size:12px; padding:10px; line-height:1.7; }}

                """)

            # Update Event Strip

            if hasattr(self, "_event_strip"):

                self._event_strip.setStyleSheet(f"background:{self.C['bg_panel']}; border-top:1px solid {self.C['border']};")

            if hasattr(self, "_event_strip_hdr"):

                self._event_strip_hdr.setStyleSheet(f"background:{self.C['bg_card']}; border-bottom:1px solid {self.C['border']};")

            if hasattr(self, "_event_stream"):

                self._event_stream.setStyleSheet(f"""

                    QTextEdit {{ background:{self.C['bg_deep']}; border:none;

                        font-family:'Cascadia Code','Consolas',monospace;

                        font-size:10px; color:{self.C['text_sec']}; padding:2px 10px; }}

                """)

            # Refresh preview content with updated theme colors

            if hasattr(self, "_cmd_bar") and hasattr(self._cmd_bar, "_apply_theme"):

                self._cmd_bar._apply_theme()

            if hasattr(self, "_ai_floating_window") and self._ai_floating_window:

                self._ai_floating_window.setStyleSheet(f"background:{self.C['bg_deep']}; color:{self.C['text_pri']};")

            if self._selected_path:

                self._update_preview(self._selected_path)

            self._log_stream(f"Switched to {self._current_theme.capitalize()} theme")

        def _toggle_theme(self):

            new_theme = "light" if self._current_theme == "dark" else "dark"

            self.set_theme(new_theme)

        # ── UI Construction ───────────────────────────────────────────────

        def _build_ui(self):

            root = QWidget()

            self.setCentralWidget(root)

            rl = QVBoxLayout(root)

            rl.setContentsMargins(0, 0, 0, 0)

            rl.setSpacing(0)

            self._build_toolbar(rl)

            self._build_main_area(rl)

            self._build_event_strip(rl)

            self._status = QStatusBar()

            self.setStatusBar(self._status)

            self._status.showMessage("Ready — click 'Open Folder' or select from Places")

        # ── Toolbar ───────────────────────────────────────────────────────

        def _build_toolbar(self, layout):

            bar = QWidget()

            bar.setFixedHeight(44)

            self._toolbar = bar

            bar.setStyleSheet(f"""

                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,

                    stop:0 {self.C['toolbar_g1']}, stop:1 {self.C['toolbar_g2']});

                border-bottom:1px solid {self.C['border']};

            """)

            bl = QHBoxLayout(bar)

            bl.setContentsMargins(8, 0, 8, 0)

            bl.setSpacing(6)

            def nav_btn(text, tip):

                b = QToolButton(); b.setText(text); b.setToolTip(tip)

                b.setFixedSize(30, 30)

                return b

            class DroppableUpButton(QToolButton):

                def __init__(self, win):

                    super().__init__()

                    self._win = win

                    self.setText("↑")

                    self.setToolTip("Up to parent folder (drop file here to move up)")

                    self.setFixedSize(30, 30)

                    self.setAcceptDrops(True)

                def dragEnterEvent(self, event):

                    if event.mimeData().hasUrls():

                        event.acceptProposedAction()

                    else:

                        event.ignore()

                def dragMoveEvent(self, event):

                    if event.mimeData().hasUrls():

                        event.acceptProposedAction()

                    else:

                        event.ignore()

                def dropEvent(self, event):

                    if not event.mimeData().hasUrls():

                        event.ignore()

                        return

                    curr = self._win._get_current_directory()

                    parent = curr.parent

                    if parent == curr or not parent.exists():

                        event.ignore()

                        return

                    urls = event.mimeData().urls()

                    moved = False

                    for u in urls:

                        sf = u.toLocalFile()

                        if sf and Path(sf).exists():

                            self._win._move_file_to_folder(sf, parent)

                            moved = True

                    if moved:

                        event.acceptProposedAction()

                    else:

                        event.ignore()

            class DroppablePathBar(QLineEdit):

                def __init__(self, win):

                    super().__init__()

                    self._win = win

                    self.setAcceptDrops(True)

                def dragEnterEvent(self, event):

                    if event.mimeData().hasUrls():

                        event.acceptProposedAction()

                    else:

                        super().dragEnterEvent(event)

                def dragMoveEvent(self, event):

                    if event.mimeData().hasUrls():

                        event.acceptProposedAction()

                    else:

                        super().dragMoveEvent(event)

                def dropEvent(self, event):

                    if not event.mimeData().hasUrls():

                        super().dropEvent(event)

                        return

                    target_str = self.text().strip() or str(self._win._get_current_directory())

                    target_p = Path(target_str)

                    if not target_p.exists() or not target_p.is_dir():

                        target_p = self._win._get_current_directory()

                    urls = event.mimeData().urls()

                    moved = False

                    for u in urls:

                        sf = u.toLocalFile()

                        if sf and Path(sf).exists():

                            self._win._move_file_to_folder(sf, target_p)

                            moved = True

                    if moved:

                        event.acceptProposedAction()

                    else:

                        event.ignore()

            self._btn_back = nav_btn("←", "Back")

            self._btn_fwd  = nav_btn("→", "Forward")

            self._btn_up   = DroppableUpButton(self)

            self._btn_ref  = nav_btn("⟳", "Refresh")

            self._btn_back.clicked.connect(self._nav_back)

            self._btn_fwd.clicked.connect(self._nav_forward)

            self._btn_up.clicked.connect(self._nav_up)

            self._btn_ref.clicked.connect(self._refresh)

            for b in (self._btn_back, self._btn_fwd, self._btn_up, self._btn_ref):

                bl.addWidget(b)

            # Open folder button

            self._btn_open_folder = QPushButton("📂  Open Folder")

            self._btn_open_folder.setFixedHeight(30)

            self._btn_open_folder.setToolTip("Open and browse any folder on your PC (Ctrl+O)")

            self._btn_open_folder.clicked.connect(self._open_folder_dialog)

            bl.addWidget(self._btn_open_folder)

            # Path bar

            self._path_bar = DroppablePathBar(self)

            self._path_bar.setPlaceholderText("Enter path or browse…")

            self._path_bar.setFixedHeight(30)

            self._path_bar.setMinimumWidth(80)

            self._path_bar.returnPressed.connect(self._navigate_to_path)

            bl.addWidget(self._path_bar, stretch=1)

            # Search Scope button

            self._search_scope = "PROJECT"

            self._user_approved_locations: List[Path] = []

            self._search_scope_btn = QToolButton(self)

            self._search_scope_btn.setText("Scope: Project ▾")

            self._search_scope_btn.setFixedHeight(30)

            self._search_scope_btn.setPopupMode(QToolButton.InstantPopup)

            self._search_scope_btn.setToolTip("Search Scope: Current Project, This Folder, or Approved Locations")

            self._search_scope_btn.setStyleSheet(f"""

                QToolButton {{ background:{self.C['bg_input']}; border:1px solid {self.C['border']};

                    border-radius:4px; color:{self.C['text_sec']}; font-size:11px; padding:0 6px; }}

                QToolButton:hover {{ border-color:{self.C['border_act']}; color:{self.C['text_pri']}; }}

            """)

            scope_menu = QMenu(self._search_scope_btn)

            act_sc_proj = QAction("●  Current Project", scope_menu)

            act_sc_proj.triggered.connect(lambda: self._set_search_scope("PROJECT"))

            scope_menu.addAction(act_sc_proj)

            act_sc_folder = QAction("○  This Folder", scope_menu)

            act_sc_folder.triggered.connect(lambda: self._set_search_scope("FOLDER"))

            scope_menu.addAction(act_sc_folder)

            act_sc_locs = QAction("○  Selected Locations", scope_menu)

            act_sc_locs.triggered.connect(lambda: self._set_search_scope("LOCATIONS"))

            scope_menu.addAction(act_sc_locs)

            scope_menu.addSeparator()

            act_sc_add = QAction("➕  Add / Index Location…", scope_menu)

            act_sc_add.triggered.connect(self._add_search_location)

            scope_menu.addAction(act_sc_add)

            self._search_scope_btn.setMenu(scope_menu)

            bl.addWidget(self._search_scope_btn)

            # Search

            self._search_box = QLineEdit()

            self._search_box.setPlaceholderText("🔍 Search project files…")

            self._search_box.setMinimumWidth(80)

            self._search_box.setMaximumWidth(170)

            self._search_box.setFixedHeight(30)

            self._search_box.setClearButtonEnabled(True)

            self._search_box.setToolTip("Search indexed project files (Press Enter to jump).")

            self._search_box.textChanged.connect(self._on_search)

            self._search_box.returnPressed.connect(self._on_search_enter)

            bl.addWidget(self._search_box)

            # Demo Mode button

            self._demo_mode_btn = QPushButton("🎬  Demo Mode")

            self._demo_mode_btn.setFixedHeight(30)

            self._demo_mode_btn.setToolTip("Launch 60-Second Hackathon Demo (demo_ml_project)")

            self._demo_mode_btn.setStyleSheet(f"""

                QPushButton {{

                    background:#0f766e; border:1px solid #14b8a6;

                    color:#fff; font-weight:700; font-size:11px;

                    border-radius:5px; padding:0 10px;

                }}

                QPushButton:hover {{ background:#14b8a6; }}

            """)

            self._demo_mode_btn.clicked.connect(self._launch_demo_mode)

            bl.addWidget(self._demo_mode_btn)

            # Theme switch button

            self._theme_btn = QPushButton("☀️  Light" if self._current_theme == "dark" else "🌙  Dark")

            self._theme_btn.setFixedHeight(30)

            self._theme_btn.setToolTip("Switch between Dark and Light mode (Ctrl+T)")

            self._theme_btn.clicked.connect(self._toggle_theme)

            bl.addWidget(self._theme_btn)

            # AI toggle

            self._ai_btn = QPushButton("✨  AI")

            self._ai_btn.setFixedHeight(30)

            self._ai_btn.setCheckable(True)

            self._ai_btn.setStyleSheet(f"""

                QPushButton {{

                    background:{self.C['ai_purple']}; border:1px solid #6d28d9;

                    color:#fff; font-weight:700; font-size:12px;

                    border-radius:5px; padding:0 14px;

                }}

                QPushButton:checked {{

                    background:#5b21b6; border-color:#7c3aed;

                }}

                QPushButton:hover {{ background:#6d28d9; }}

            """)

            self._ai_btn.clicked.connect(self._toggle_ai_panel)

            bl.addWidget(self._ai_btn)

            layout.addWidget(bar)

            self._nav_history: List[str] = []

            self._nav_pos: int = -1

        # ── Main area ─────────────────────────────────────────────────────

        def _build_main_area(self, layout):

            self._main_splitter = QSplitter(Qt.Horizontal)

            self._main_splitter.setHandleWidth(6)

            self._main_splitter.setChildrenCollapsible(True)

            self._build_left_tree(self._main_splitter)

            self._build_center_panel(self._main_splitter)

            self._build_right_panel(self._main_splitter)

            self._main_splitter.setSizes([200, 740, 360])

            for i in range(1, 3):

                h = self._main_splitter.handle(i)

                if h:

                    h.setCursor(Qt.SplitHCursor)

            layout.addWidget(self._main_splitter, stretch=1)

        # ── LEFT: File tree (quick-access + drive list + drag & drop + lazy subfolders) ──

        class NavigationTreeWidget(QTreeWidget):

            """

            Windows 11 File Explorer Navigation Sidebar Tree:

            - Full drag-and-drop file move support to any drive, folder, or subfolder

            - Dynamic lazy-loading of subdirectories when nodes are expanded

            - Drag-hover auto-expansion of folder nodes

            - Visual selection/hover during drag

            """

            def __init__(self, win):

                super().__init__()

                self._win = win

                self.setHeaderHidden(True)

                self.setIndentation(12)

                self.setAcceptDrops(True)

                self.setDragDropMode(QAbstractItemView.DropOnly)

                self.setAutoScroll(True)

                self._hover_timer = QTimer(self)

                self._hover_timer.setSingleShot(True)

                self._hover_timer.setInterval(700)

                self._hover_item = None

                self._hover_timer.timeout.connect(self._auto_expand_hovered_item)

            def _auto_expand_hovered_item(self):

                if self._hover_item and not self._hover_item.isExpanded():

                    self._hover_item.setExpanded(True)

            def dragEnterEvent(self, event):

                if event.mimeData().hasUrls():

                    event.acceptProposedAction()

                else:

                    super().dragEnterEvent(event)

            def dragMoveEvent(self, event):

                if not event.mimeData().hasUrls():

                    super().dragMoveEvent(event)

                    return

                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

                item = self.itemAt(pos)

                if item:

                    p_str = item.data(0, Qt.UserRole)

                    if p_str and p_str != "__DUMMY__":

                        p = Path(p_str)

                        if p.exists() and p.is_dir():

                            self.setCurrentItem(item)

                            if item != self._hover_item:

                                self._hover_item = item

                                self._hover_timer.start()

                            event.acceptProposedAction()

                            return

                self._hover_timer.stop()

                self._hover_item = None

                event.ignore()

            def dragLeaveEvent(self, event):

                self._hover_timer.stop()

                self._hover_item = None

                super().dragLeaveEvent(event)

            def dropEvent(self, event):

                self._hover_timer.stop()

                self._hover_item = None

                if not event.mimeData().hasUrls():

                    super().dropEvent(event)

                    return

                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

                item = self.itemAt(pos)

                if not item:

                    event.ignore()

                    return

                dest_path_str = item.data(0, Qt.UserRole)

                if not dest_path_str or dest_path_str == "__DUMMY__":

                    event.ignore()

                    return

                dest_dir = Path(dest_path_str)

                if not dest_dir.exists() or not dest_dir.is_dir():

                    event.ignore()

                    return

                urls = event.mimeData().urls()

                moved_any = False

                for u in urls:

                    src_str = u.toLocalFile()

                    if src_str and Path(src_str).exists():

                        src_p = Path(src_str)

                        if src_p.resolve() != dest_dir.resolve() and src_p.parent.resolve() != dest_dir.resolve():

                            self._win._move_file_to_folder(str(src_p), dest_dir)

                            moved_any = True

                if moved_any:

                    event.acceptProposedAction()

                else:

                    event.ignore()

        def _build_left_tree(self, splitter):

            panel = QWidget()

            self._left_panel = panel

            panel.setStyleSheet(f"background:{self.C['bg_panel']}; border-right:1px solid {self.C['border']};")

            panel.setMinimumWidth(100)

            pl = QVBoxLayout(panel)

            pl.setContentsMargins(0, 0, 0, 0)

            pl.setSpacing(0)

            # Header

            self._left_header = self._section_header("  PLACES")

            pl.addWidget(self._left_header)

            self._left_tree = self.NavigationTreeWidget(self)

            self._left_tree.itemClicked.connect(self._on_left_tree_item)

            self._left_tree.itemExpanded.connect(self._on_left_tree_item_expanded)

            self._left_tree.setContextMenuPolicy(Qt.CustomContextMenu)

            self._left_tree.customContextMenuRequested.connect(self._show_left_tree_context_menu)

            pl.addWidget(self._left_tree)

            self._populate_left_tree()

            splitter.addWidget(panel)

        def _section_header(self, text: str) -> QLabel:

            lbl = QLabel(text)

            lbl.setFixedHeight(28)

            lbl.setStyleSheet(f"""

                background:{self.C['bg_card']}; color:{self.C['text_muted']};

                font-size:9px; font-weight:bold; letter-spacing:1px;

                padding:0 10px; border-bottom:1px solid {self.C['border']};

            """)

            return lbl

        @staticmethod

        def _has_subdirs(dir_path: Path) -> bool:

            try:

                with os.scandir(dir_path) as it:

                    for entry in it:

                        try:

                            if entry.name.startswith("$") or entry.name in (

                                "System Volume Information", "Recovery", "$RECYCLE.BIN"

                            ):

                                continue

                            if entry.is_dir(follow_symlinks=False):

                                return True

                        except (PermissionError, OSError):

                            continue

            except (PermissionError, OSError):

                pass

            return False

        def _populate_left_tree(self):

            self._left_tree.clear()

            def add_folder_item(parent, icon, label, path_str, has_subdirs_check=True):

                item = QTreeWidgetItem(parent or self._left_tree, [f"{icon}  {label}"])

                item.setData(0, Qt.UserRole, path_str)

                item.setForeground(0, QColor(self.C["text_sec"]))

                if has_subdirs_check and path_str:

                    p = Path(path_str)

                    if p.exists() and p.is_dir() and self._has_subdirs(p):

                        dummy = QTreeWidgetItem(item, ["..."])

                        dummy.setData(0, Qt.UserRole, "__DUMMY__")

                return item

            # Quick access

            qa = QTreeWidgetItem(self._left_tree, ["  Quick access"])

            qa.setForeground(0, QColor(self.C["text_muted"]))

            qa.setFont(0, _small_bold_font())

            qa.setFlags(Qt.ItemIsEnabled)

            qa.setExpanded(True)

            home = Path.home()

            for label, path in [

                ("Home",      str(home)),

                ("Desktop",   str(home / "Desktop")),

                ("Documents", str(home / "Documents")),

                ("Downloads", str(home / "Downloads")),

            ]:

                if Path(path).exists():

                    add_folder_item(qa, "🏠" if label == "Home" else "📁", label, path)

            # Drives

            drives_root = QTreeWidgetItem(self._left_tree, ["  This PC"])

            drives_root.setForeground(0, QColor(self.C["text_muted"]))

            drives_root.setFont(0, _small_bold_font())

            drives_root.setFlags(Qt.ItemIsEnabled)

            drives_root.setExpanded(True)

            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":

                dp = Path(f"{letter}:\\")

                if dp.exists():

                    add_folder_item(drives_root, "💾", f"Local Disk ({letter}:)", str(dp))

            # Current project

            if self._service.current_graph and self._service.project_root:

                proj_root = QTreeWidgetItem(self._left_tree, ["  Monitored Project"])

                proj_root.setForeground(0, QColor(self.C["text_muted"]))

                proj_root.setFont(0, _small_bold_font())

                proj_root.setFlags(Qt.ItemIsEnabled)

                proj_root.setExpanded(True)

                add_folder_item(proj_root, "📂", self._service.project_root.name,

                                str(self._service.project_root))

        def _on_left_tree_item_expanded(self, item: QTreeWidgetItem):

            """Lazy-load child directories when a drive or folder node is expanded."""

            if item.childCount() == 1:

                child = item.child(0)

                if child and child.data(0, Qt.UserRole) == "__DUMMY__":

                    item.removeChild(child)

                    path_str = item.data(0, Qt.UserRole)

                    if path_str:

                        p = Path(path_str)

                        if p.exists() and p.is_dir():

                            self._lazy_load_subdirs(item, p)

        def _lazy_load_subdirs(self, parent_item: QTreeWidgetItem, dir_path: Path):

            """Populate immediate subdirectories under parent_item."""

            try:

                subdirs = []

                with os.scandir(dir_path) as it:

                    for entry in it:

                        try:

                            if entry.is_dir(follow_symlinks=False):

                                name = entry.name

                                if name.startswith("$") or name in ("System Volume Information", "$RECYCLE.BIN", "Recovery"):

                                    continue

                                subdirs.append(entry.path)

                        except (PermissionError, OSError):

                            continue

                subdirs.sort(key=lambda s: Path(s).name.lower())

                for s_path in subdirs:

                    p_obj = Path(s_path)

                    sub_item = QTreeWidgetItem(parent_item, [f"📁  {p_obj.name}"])

                    sub_item.setData(0, Qt.UserRole, str(p_obj))

                    sub_item.setForeground(0, QColor(self.C["text_sec"]))

                    if self._has_subdirs(p_obj):

                        d = QTreeWidgetItem(sub_item, ["..."])

                        d.setData(0, Qt.UserRole, "__DUMMY__")

            except (PermissionError, OSError) as e:

                logger.debug(f"Cannot list directories in {dir_path}: {e}")

        def _show_left_tree_context_menu(self, pos):

            item = self._left_tree.itemAt(pos)

            if not item:

                return

            path_str = item.data(0, Qt.UserRole)

            if not path_str or path_str == "__DUMMY__":

                return

            p = Path(path_str)

            if not p.exists() or not p.is_dir():

                return

            menu = QMenu(self)

            menu.setStyleSheet(f"""

                QMenu {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};

                         color:{self.C['text_pri']}; font-size:11px; padding:4px; }}

                QMenu::item {{ padding:5px 20px; border-radius:3px; }}

                QMenu::item:selected {{ background:{self.C['accent']}; color:#fff; }}

                QMenu::separator {{ height:1px; background:{self.C['border']}; margin:3px 0; }}

            """)

            act_open = menu.addAction("📂  Open Folder")

            act_open.triggered.connect(lambda: self._navigate_to(path_str))

            can_paste = bool(getattr(self, "_clipboard_path", None) and Path(self._clipboard_path).exists())

            if not can_paste:

                try:

                    c = QApplication.clipboard()

                    md = c.mimeData()

                    if md and md.hasUrls():

                        can_paste = True

                except Exception:

                    pass

            if can_paste:

                mode_str = getattr(self, "_clipboard_mode", "COPY") or "COPY"

                paste_label = "📦  Paste (Move Here)" if mode_str == "CUT" else "📋  Paste (Copy Here)"

                act_paste = menu.addAction(paste_label)

                def do_paste_in_folder():

                    old_sel = self._selected_path

                    self._selected_path = path_str

                    self._paste_selection()

                    self._selected_path = old_sel

                act_paste.triggered.connect(do_paste_in_folder)

            menu.addSeparator()

            act_copy_path = menu.addAction("📄  Copy Path")

            act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(str(p.resolve())))

            act_reveal = menu.addAction("🗔  Reveal in Windows Explorer")

            act_reveal.triggered.connect(lambda: self._reveal_in_os_explorer(path_str))

            menu.exec(self._left_tree.viewport().mapToGlobal(pos))

        # ── CENTER: file list + tabs ──────────────────────────────────────

        def _build_center_panel(self, splitter):

            self._center_widget = QWidget()

            self._center_widget.setStyleSheet(f"background:{self.C['bg_deep']};")

            cl = QVBoxLayout(self._center_widget)

            cl.setContentsMargins(0, 0, 0, 0)

            cl.setSpacing(0)

            # Breadcrumb / address sub-bar

            self._addr_bar = QWidget()

            self._addr_bar.setFixedHeight(32)

            self._addr_bar.setStyleSheet(f"background:{self.C['bg_card']}; border-bottom:1px solid {self.C['border']};")

            abl = QHBoxLayout(self._addr_bar)

            abl.setContentsMargins(8, 0, 8, 0)

            abl.setSpacing(8)

            self._addr_label = QLabel("D:\\")

            self._addr_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

            self._addr_label.setMinimumWidth(0)

            self._addr_label.setStyleSheet(f"color:{self.C['text_sec']}; font-size:11px;")

            abl.addWidget(self._addr_label)

            abl.addStretch()

            self._btn_index_now = QPushButton("⚡  Index as Project")

            self._btn_index_now.setFixedHeight(22)

            self._btn_index_now.setToolTip("Analyze relationships and build consequence graph for this folder")

            self._btn_index_now.clicked.connect(self._index_current_folder)

            abl.addWidget(self._btn_index_now)

            self._idx_label = QLabel("Folder View")

            self._idx_label.setStyleSheet(f"color:{self.C['text_muted']}; font-size:10px;")

            abl.addWidget(self._idx_label)

            cl.addWidget(self._addr_bar)

            # Progress bar

            self._progress = QProgressBar()

            self._progress.setFixedHeight(2)

            self._progress.setRange(0, 0)

            self._progress.hide()

            cl.addWidget(self._progress)

            # Tabs

            self._center_tabs = QTabWidget()

            self._center_tabs.setStyleSheet(f"""

                QTabWidget::pane {{ border:none; border-top:1px solid {self.C['border']}; }}

                QTabBar::tab {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};

                    border-bottom:none; padding:5px 14px; color:{self.C['text_sec']}; font-size:11px; }}

                QTabBar::tab:selected {{ background:{self.C['bg_panel']}; color:{self.C['accent']};

                    border-bottom:2px solid {self.C['accent']}; }}

            """)

            # Tab 1: File list

            self._build_file_list_tab()

            # Tab 2: Dependency graph

            self._build_graph_tab()

            # Tab 3: Simulate

            self._build_simulate_tab()

            # Tab 4: Operation History

            self._build_history_tab()

            cl.addWidget(self._center_tabs, stretch=1)

            splitter.addWidget(self._center_widget)

        # ════════════════════════════════════════════════════════════════════════

        # Native Drag & Drop Explorer Tree View

        # ════════════════════════════════════════════════════════════════════════

        class ExplorerTreeView(QTreeView):

            """

            Windows 11 File Explorer Tree View supporting native drag-and-drop moves

            with PreView AI consequence awareness and confirmation.

            """

            def __init__(self, win: "PreViewWindow"):

                super().__init__()

                self._win = win

                self.setDragEnabled(True)

                self.setAcceptDrops(True)

                self.setDropIndicatorShown(True)

                self.setDragDropMode(QAbstractItemView.DragDrop)

                self.setDefaultDropAction(Qt.MoveAction)

            def startDrag(self, supportedActions):

                indexes = self.selectionModel().selectedRows(0)

                if not indexes:

                    idx = self.currentIndex()

                    if idx.isValid():

                        indexes = [idx]

                if not indexes:

                    return

                mime = QMimeData()

                urls = []

                for idx in indexes:

                    p = self._win._fs_model.filePath(idx)

                    if p:

                        urls.append(QUrl.fromLocalFile(p))

                if urls:

                    mime.setUrls(urls)

                    mime.setText("\n".join(u.toLocalFile() for u in urls))

                    drag = QDrag(self)

                    drag.setMimeData(mime)

                    drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)

            def dragEnterEvent(self, event):

                if event.mimeData().hasUrls():

                    event.acceptProposedAction()

                else:

                    super().dragEnterEvent(event)

            def dragMoveEvent(self, event):

                if event.mimeData().hasUrls():

                    event.acceptProposedAction()

                else:

                    super().dragMoveEvent(event)

            def keyPressEvent(self, event):

                if event.matches(QKeySequence.Copy):

                    self._win._copy_selection()

                    event.accept()

                    return

                elif event.matches(QKeySequence.Paste):

                    self._win._paste_selection()

                    event.accept()

                    return

                elif event.matches(QKeySequence.Cut):

                    self._win._cut_selection()

                    event.accept()

                    return

                elif event.key() == Qt.Key_Delete and event.modifiers() == Qt.NoModifier:

                    self._win._delete_file()

                    event.accept()

                    return

                elif event.key() == Qt.Key_F2:

                    self._win._rename_file()

                    event.accept()

                    return

                super().keyPressEvent(event)

            def dropEvent(self, event):

                if not event.mimeData().hasUrls():

                    super().dropEvent(event)

                    return

                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

                idx = self.indexAt(pos)

                if idx.isValid():

                    target_path = Path(self._win._fs_model.filePath(idx))

                    dest_dir = target_path if target_path.is_dir() else target_path.parent

                else:

                    dest_dir = self._win._get_current_directory()

                urls = event.mimeData().urls()

                moved_any = False

                for u in urls:

                    src_str = u.toLocalFile()

                    if src_str and Path(src_str).exists():

                        src_p = Path(src_str)

                        if src_p.parent.resolve() != dest_dir.resolve() and src_p.resolve() != dest_dir.resolve():

                            # Defer out of dropEvent to allow Windows OLE drag-drop to complete cleanly without deadlocking

                            QTimer.singleShot(0, lambda s=str(src_p), d=dest_dir: self._win._move_file_to_folder(s, d))

                            moved_any = True

                if moved_any:

                    event.acceptProposedAction()

                else:

                    event.ignore()

        def _build_explorer_command_bar(self) -> QWidget:

            return ResponsiveExplorerCommandBar(self)

        def _build_file_list_tab(self):

            """Fast file list using QFileSystemModel with Windows 11 Explorer Command Bar."""

            tab = QWidget()

            tl  = QVBoxLayout(tab)

            tl.setContentsMargins(0, 0, 0, 0)

            tl.setSpacing(0)

            # Explorer Command Bar

            self._cmd_bar = self._build_explorer_command_bar()

            tl.addWidget(self._cmd_bar)

            # QFileSystemModel — lazy, OS-native, fast

            self._fs_model = QFileSystemModel()

            self._fs_model.setReadOnly(True)

            self._fs_model.setRootPath(QDir.rootPath())

            self._fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

            self._fs_model.directoryLoaded.connect(self._on_directory_loaded)

            self._file_view = self.ExplorerTreeView(self)

            self._file_view.setModel(self._fs_model)

            self._file_view.setRootIsDecorated(False)

            self._file_view.setAlternatingRowColors(True)

            self._file_view.setSortingEnabled(True)

            self._file_view.setSelectionMode(QAbstractItemView.SingleSelection)

            self._file_view.setColumnWidth(0, 340)

            self._file_view.setColumnWidth(1, 90)

            self._file_view.setColumnWidth(2, 130)

            self._file_view.setColumnWidth(3, 140)

            self._file_view.header().setStretchLastSection(True)

            self._file_view.doubleClicked.connect(self._on_file_double_clicked)

            self._file_view.clicked.connect(self._on_file_clicked)

            self._file_view.setContextMenuPolicy(Qt.CustomContextMenu)

            self._file_view.customContextMenuRequested.connect(self._show_context_menu)

            self._file_view.setStyleSheet(f"""

                QTreeView {{ background:{self.C['bg_deep']}; border:none; }}

                QTreeView::item {{ padding:4px 6px; }}

                QTreeView::item:hover {{ background:{self.C['bg_hover']}; }}

                QTreeView::item:selected {{ background:{self.C['accent_dk']}; color:#fff; }}

            """)

            # Keyboard Shortcuts matching Windows Explorer (active window-wide)

            for seq, fn in [

                (QKeySequence.Copy, lambda: self._copy_selection()),

                (QKeySequence.Paste, lambda: self._paste_selection()),

                (QKeySequence.Cut, lambda: self._cut_selection()),

                (QKeySequence.Delete, lambda: self._delete_file()),

                (QKeySequence(Qt.Key_F2), lambda: self._rename_file()),

                (QKeySequence("Ctrl+Shift+N"), lambda: self._new_folder()),

                (QKeySequence("Ctrl+Shift+C"), lambda: self._copy_as_path()),

                (QKeySequence(Qt.AltModifier | Qt.Key_Return), lambda: self._show_properties()),

                (QKeySequence(Qt.Key_Return), self._on_enter_pressed),

                (QKeySequence(Qt.Key_Enter), self._on_enter_pressed),

                (QKeySequence(Qt.Key_Backspace), self._nav_up),

                (QKeySequence(Qt.Key_F5), self._refresh),

            ]:

                sc = QShortcut(seq, self)

                sc.setContext(Qt.WindowShortcut)

                sc.activated.connect(fn)

            # Selection model update

            self._file_view.selectionModel().selectionChanged.connect(self._on_file_selection_changed)

            tl.addWidget(self._file_view, stretch=1)

            self._center_tabs.addTab(tab, "📁  Files")

        def _build_graph_tab(self):

            tab = QWidget()

            tl  = QVBoxLayout(tab)

            tl.setContentsMargins(8, 8, 8, 8)

            hdr = QLabel("Dependency Graph — detected relationships in the monitored project (Click any node to inspect)")

            hdr.setStyleSheet(f"color:{C['text_sec']}; font-size:10px; margin-bottom:4px;")

            tl.addWidget(hdr)

            self._graph_text = QTextBrowser()

            self._graph_text.setReadOnly(True)

            self._graph_text.setOpenLinks(False)

            self._graph_text.anchorClicked.connect(self._on_graph_anchor_clicked)

            self._graph_text.setStyleSheet(f"""

                QTextBrowser {{ background:{C['bg_panel']}; border:1px solid {C['border']};

                    border-radius:6px; font-family:'Segoe UI',sans-serif;

                    font-size:11px; color:{C['text_pri']}; padding:10px; }}

            """)

            self._graph_text.setPlaceholderText("Scan a project folder to see its dependency graph.")

            tl.addWidget(self._graph_text, stretch=1)

            self._center_tabs.addTab(tab, "🔗  Graph")

        def _build_simulate_tab(self):

            tab = QWidget()

            tl  = QVBoxLayout(tab)

            tl.setContentsMargins(12, 12, 12, 12)

            tl.setSpacing(10)

            grp = QGroupBox("Propose a Change  (Mode A — AI Simulation)")

            grp.setStyleSheet(f"""

                QGroupBox {{ border:1px solid {C['border']}; border-radius:6px;

                    margin-top:6px; padding:10px; color:{C['text_sec']};

                    font-size:10px; font-weight:bold; letter-spacing:1px; }}

                QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; }}

            """)

            gl = QHBoxLayout(grp)

            self._intent_edit = QLineEdit()

            self._intent_edit.setPlaceholderText(

                '"delete dataset.csv"  |  "move train.py to scripts/"  |  "rename model.pkl to model_v2.pkl"'

            )

            self._intent_edit.setFixedHeight(34)

            self._intent_edit.returnPressed.connect(self._run_simulation)

            gl.addWidget(self._intent_edit, stretch=1)

            self._sim_btn = QPushButton("▶  Simulate")

            self._sim_btn.setFixedHeight(34)

            self._sim_btn.setStyleSheet(f"""

                QPushButton {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,

                    stop:0 {C['accent_dk']},stop:1 {C['accent']});

                    border:none; border-radius:5px; color:#fff;

                    font-weight:700; font-size:12px; padding:0 18px; }}

                QPushButton:hover {{ background:{C['accent']}; }}

                QPushButton:disabled {{ background:{C['bg_hover']}; color:{C['text_muted']}; }}

            """)

            self._sim_btn.clicked.connect(self._run_simulation)

            gl.addWidget(self._sim_btn)

            tl.addWidget(grp)

            self._sim_result = QTextEdit()

            self._sim_result.setReadOnly(True)

            self._sim_result.setStyleSheet(f"""

                QTextEdit {{ background:{C['bg_panel']}; border:1px solid {C['border']};

                    border-radius:6px; color:{C['text_pri']}; font-size:12px; padding:10px; }}

            """)

            self._sim_result.setPlaceholderText(

                "Type a proposed action above and click Simulate.\n\n"

                "Examples:\n  delete dataset.csv\n  move train.py to scripts/\n  rename config.json to config_prod.json"

            )

            tl.addWidget(self._sim_result, stretch=1)

            btn_row = QHBoxLayout()

            self._cancel_btn = QPushButton("✕  Cancel")

            self._cancel_btn.setEnabled(False)

            self._cancel_btn.setStyleSheet(f"""

                QPushButton {{ background:{C['bg_card']}; border:1px solid {C['border']};

                    color:{C['text_sec']}; font-weight:bold; }}

                QPushButton:hover {{ border-color:{C['red']}; color:{C['red']}; }}

            """)

            self._cancel_btn.clicked.connect(self._cancel_sim)

            btn_row.addWidget(self._cancel_btn)

            btn_row.addStretch()

            self._exec_btn = QPushButton("✓  Approve & Execute")

            self._exec_btn.setEnabled(False)

            self._exec_btn.setStyleSheet(f"""

                QPushButton {{

                    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,

                        stop:0 {C['green_dk']},stop:1 #166534);

                    border:1px solid {C['green']}; color:{C['green']};

                    font-weight:700; font-size:12px; padding:6px 20px; border-radius:5px;

                }}

                QPushButton:hover {{ color:#fff; }}

                QPushButton:disabled {{ background:{C['bg_card']}; border-color:{C['border']};

                    color:{C['text_muted']}; }}

            """)

            self._exec_btn.clicked.connect(self._execute_action)

            btn_row.addWidget(self._exec_btn)

            tl.addLayout(btn_row)

            self._center_tabs.addTab(tab, "⚡  Simulate")

        def _build_history_tab(self):

            tab = QWidget()

            tl = QVBoxLayout(tab)

            tl.setContentsMargins(12, 12, 12, 12)

            tl.setSpacing(8)

            hdr = QWidget()

            hl = QHBoxLayout(hdr)

            hl.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel("📜  Operation History & Verifications")

            lbl.setStyleSheet(f"font-size:12px; font-weight:bold; color:{C['text_pri']};")

            hl.addWidget(lbl)

            hl.addStretch()

            clear_btn = QPushButton("Clear History")

            clear_btn.setFixedHeight(24)

            clear_btn.setStyleSheet(f"background:{C['bg_input']}; border:1px solid {C['border']}; color:{C['text_sec']}; font-size:10px; border-radius:3px; padding:0 8px;")

            clear_btn.clicked.connect(self._clear_operation_history)

            hl.addWidget(clear_btn)

            tl.addWidget(hdr)

            self._op_history_tree = QTreeWidget()

            self._op_history_tree.setHeaderLabels(["Time", "Operation", "Target", "Status", "Verification Details"])

            self._op_history_tree.setColumnWidth(0, 70)

            self._op_history_tree.setColumnWidth(1, 90)

            self._op_history_tree.setColumnWidth(2, 160)

            self._op_history_tree.setColumnWidth(3, 110)

            self._op_history_tree.setStyleSheet(f"""

                QTreeWidget {{ background:{C['bg_panel']}; border:1px solid {C['border']};

                    color:{C['text_pri']}; font-size:11px; border-radius:6px; }}

                QTreeWidget::item {{ padding:5px; }}

                QHeaderView::section {{ background:{C['bg_card']}; color:{C['text_muted']};

                    border:none; border-bottom:1px solid {C['border']}; padding:5px; font-weight:bold; font-size:11px; }}

            """)

            self._op_history_tree.setAlternatingRowColors(True)

            tl.addWidget(self._op_history_tree, stretch=1)

            self._center_tabs.addTab(tab, "📜  History")

        # ── RIGHT: Preview / AI Panel (stacked) ───────────────────────────

        def _build_right_panel(self, splitter):

            self._right_stack = QStackedWidget()

            self._right_stack.setMinimumWidth(150)

            self._right_stack.setStyleSheet(f"background:{C['bg_panel']}; border-left:1px solid {C['border']};")

            # Page 0: File preview

            self._build_preview_page()

            # Page 1: AI panel

            self._build_ai_page()

            splitter.addWidget(self._right_stack)

        def _build_preview_page(self):

            page = QWidget()

            pl   = QVBoxLayout(page)

            pl.setContentsMargins(0, 0, 0, 0)

            pl.setSpacing(0)

            pl.addWidget(self._section_header("  PREVIEW"))

            # File info area

            self._preview_info = QTextEdit()

            self._preview_info.setReadOnly(True)

            self._preview_info.setFixedHeight(230)

            self._preview_info.setStyleSheet(f"""

                QTextEdit {{ background:{C['bg_card']}; border:none; border-bottom:1px solid {C['border']};

                    color:{C['text_sec']}; font-size:11px; padding:10px; }}

            """)

            self._preview_info.setPlaceholderText("Select a file to see details.")

            pl.addWidget(self._preview_info)

            # Impact summary

            pl.addWidget(self._section_header("  IMPACT SUMMARY"))

            self._preview_impact = QTextEdit()

            self._preview_impact.setReadOnly(True)

            self._preview_impact.setStyleSheet(f"""

                QTextEdit {{ background:{C['bg_panel']}; border:none;

                    color:{C['text_sec']}; font-size:11px; padding:10px; line-height:1.7; }}

            """)

            self._preview_impact.setPlaceholderText("Impact data will appear here.")

            pl.addWidget(self._preview_impact, stretch=1)

            # Quick actions (Section 12: Actions [Simulate Change] [Ask AI] [Modify])

            self._qa_bar = QWidget()

            self._qa_bar.setFixedHeight(40)

            self._qa_bar.setStyleSheet(f"background:{C['bg_card']}; border-top:1px solid {C['border']};")

            qal = QHBoxLayout(self._qa_bar)

            qal.setContentsMargins(8, 4, 8, 4)

            qal.setSpacing(6)

            for label, slot in [

                ("⚡  Simulate Change", self._on_quick_sim_clicked),

                ("✨  Ask AI", self._on_quick_ask_ai),

                ("✏️  Modify", self._on_quick_modify),

            ]:

                btn = QPushButton(label)

                btn.setFixedHeight(28)

                btn.setStyleSheet(f"""

                    QPushButton {{ background:{C['bg_input']}; border:1px solid {C['border']};

                        color:{C['text_sec']}; font-size:10px; border-radius:4px; font-weight:600; padding:0 4px; }}

                    QPushButton:hover {{ border-color:{C['border_act']}; color:{C['text_pri']}; }}

                """)

                btn.clicked.connect(slot)

                qal.addWidget(btn)

            pl.addWidget(self._qa_bar)

            self._right_stack.addWidget(page)

        def _build_ai_page(self):

            page = QWidget()

            self._ai_page_widget = page

            pl   = QVBoxLayout(page)

            pl.setContentsMargins(0, 0, 0, 0)

            pl.setSpacing(0)

            # Header

            hdr = QWidget()

            hdr.setFixedHeight(44)

            hdr.setStyleSheet(f"""

                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,

                    stop:0 #2e1065,stop:1 #4c1d95);

                border-bottom:1px solid #5b21b6;

            """)

            hl = QHBoxLayout(hdr)

            hl.setContentsMargins(12, 0, 8, 0)

            hl.setSpacing(6)

            logo = QLabel("✨  PreView AI")

            logo.setStyleSheet("color:#c4b5fd; font-size:13px; font-weight:800; letter-spacing:1px;")

            hl.addWidget(logo)

            # Snapdragon AI Technical Status Area (unobtrusive, hardware-grounded)

            self._ai_status_badge = QToolButton()

            self._ai_status_badge.setToolTip("Click to view Snapdragon AI Diagnostics & Acceleration Status")

            self._ai_status_badge.clicked.connect(self._show_ai_diagnostics)

            hl.addWidget(self._ai_status_badge)

            self._update_ai_status_badge()

            hl.addStretch()

            self._ai_popout_btn = QToolButton()

            self._ai_popout_btn.setText("⧉")

            self._ai_popout_btn.setToolTip("Detach / Pop out AI panel into a movable, floating window (or dock back)")

            self._ai_popout_btn.setStyleSheet("color:#c4b5fd; font-size:13px; font-weight:bold; padding:2px 6px;")

            self._ai_popout_btn.clicked.connect(self._toggle_ai_floating)

            hl.addWidget(self._ai_popout_btn)

            close_btn = QToolButton()

            close_btn.setText("×")

            close_btn.setStyleSheet(f"color:#c4b5fd; font-size:16px; font-weight:bold; padding:2px 6px;")

            close_btn.clicked.connect(self._close_ai_panel)

            hl.addWidget(close_btn)

            pl.addWidget(hdr)

            # Context bar

            self._ai_ctx = QLabel("No file selected")

            self._ai_ctx.setFixedHeight(32)

            self._ai_ctx.setStyleSheet(f"""

                background:{C['bg_card']}; color:{C['text_muted']};

                font-size:10px; padding:0 12px;

                border-bottom:1px solid {C['border']};

            """)

            pl.addWidget(self._ai_ctx)

            # Conversation

            self._ai_chat = QTextEdit()

            self._ai_chat.setReadOnly(True)

            self._ai_chat.setStyleSheet(f"""

                QTextEdit {{ background:{C['bg_deep']}; border:none;

                    color:{C['text_pri']}; font-size:12px; padding:10px; line-height:1.7; }}

            """)

            self._ai_chat.setPlaceholderText(

                "Ask about the selected file…\n\n"

                "Examples:\n"

                "  • What files use this?\n"

                "  • What happens if I delete this?\n"

                "  • What could break if I move this?\n"

                "  • Show the dependency path.\n"

                "  • Move this into the data folder."

            )

            pl.addWidget(self._ai_chat, stretch=1)

            # Quick prompts

            qp_bar = QWidget()

            qp_bar.setFixedHeight(34)

            qp_bar.setStyleSheet(f"background:{C['bg_card']}; border-top:1px solid {C['border']};")

            qpl = QHBoxLayout(qp_bar)

            qpl.setContentsMargins(6, 3, 6, 3)

            qpl.setSpacing(4)

            for label, prompt_template in [

                ("What uses this?", "What files use {file}?"),

                ("Delete impact?", "What happens if I delete {file}?"),

                ("Move impact?",   "What happens if I move {file}?"),

            ]:

                btn = QPushButton(label)

                btn.setFixedHeight(26)

                btn.setStyleSheet(f"""

                    QPushButton {{ background:#3b1985; border:1px solid #5b21b6;

                        color:#c4b5fd; font-size:10px; border-radius:4px; }}

                    QPushButton:hover {{ background:#4c1d95; }}

                """)

                btn.setProperty("prompt_template", prompt_template)

                btn.clicked.connect(self._on_quick_prompt)

                qpl.addWidget(btn)

            pl.addWidget(qp_bar)

            # Confirmation bar for destructive operations and code edits

            self._ai_confirm_bar = QWidget()

            self._ai_confirm_bar.setFixedHeight(36)

            self._ai_confirm_bar.setStyleSheet(f"background:{C['bg_card']}; border-top:1px solid #7c3aed;")

            cbl = QHBoxLayout(self._ai_confirm_bar)

            cbl.setContentsMargins(8, 2, 8, 2)

            cbl.setSpacing(6)

            self._ai_confirm_lbl = QLabel("Action requires confirmation:")

            self._ai_confirm_lbl.setStyleSheet("color:#f59e0b; font-size:10px; font-weight:bold;")

            cbl.addWidget(self._ai_confirm_lbl, stretch=1)

            self._ai_confirm_btn = QPushButton("✓ Confirm")

            self._ai_confirm_btn.setFixedHeight(24)

            self._ai_confirm_btn.setStyleSheet("background:#16a34a; color:#fff; font-size:10px; font-weight:bold; border-radius:3px; padding:0 8px;")

            self._ai_confirm_btn.clicked.connect(self._on_ai_confirm_action)

            cbl.addWidget(self._ai_confirm_btn)

            self._ai_cancel_btn = QPushButton("✕ Cancel")

            self._ai_cancel_btn.setFixedHeight(24)

            self._ai_cancel_btn.setStyleSheet("background:#dc2626; color:#fff; font-size:10px; font-weight:bold; border-radius:3px; padding:0 8px;")

            self._ai_cancel_btn.clicked.connect(self._on_ai_cancel_action)

            cbl.addWidget(self._ai_cancel_btn)

            self._ai_confirm_bar.setVisible(False)

            pl.addWidget(self._ai_confirm_bar)

            # Input row

            input_row = QWidget()

            input_row.setFixedHeight(54)

            input_row.setStyleSheet(f"background:{C['bg_card']}; border-top:1px solid {C['border']};")

            irl = QHBoxLayout(input_row)

            irl.setContentsMargins(8, 6, 8, 6)

            irl.setSpacing(6)

            self._ai_input = ChatInputEdit(self._send_ai_message)

            self._ai_input.setFixedHeight(40)

            self._ai_input.setStyleSheet(f"""

                QPlainTextEdit {{ background:{C['bg_input']}; border:1px solid {C['border']};

                    border-radius:5px; color:{C['text_pri']}; padding:4px 8px; font-size:12px; }}

                QPlainTextEdit:focus {{ border-color:#7c3aed; }}

            """)

            irl.addWidget(self._ai_input, stretch=1)

            send_btn = QPushButton("➤")

            send_btn.setFixedSize(36, 40)

            send_btn.setToolTip("Send message (Enter to send, Shift+Enter for newline)")

            send_btn.setStyleSheet(f"""

                QPushButton {{ background:#7c3aed; border:none; border-radius:5px;

                    color:#fff; font-size:14px; font-weight:bold; }}

                QPushButton:hover {{ background:{C['ai_purple']}; }}

            """)

            send_btn.clicked.connect(self._send_ai_message)

            irl.addWidget(send_btn)

            pl.addWidget(input_row)

            self._right_stack.addWidget(page)

        # ── Bottom event strip ─────────────────────────────────────────────

        def _build_event_strip(self, layout):

            self._event_strip = QWidget()

            self._event_strip.setFixedHeight(120)

            self._event_strip.setStyleSheet(f"background:{self.C['bg_panel']}; border-top:1px solid {self.C['border']};")

            sl = QVBoxLayout(self._event_strip)

            sl.setContentsMargins(0, 0, 0, 0)

            sl.setSpacing(0)

            self._event_strip_hdr = QWidget()

            self._event_strip_hdr.setFixedHeight(24)

            self._event_strip_hdr.setStyleSheet(f"background:{self.C['bg_card']}; border-bottom:1px solid {self.C['border']};")

            hrl = QHBoxLayout(self._event_strip_hdr)

            hrl.setContentsMargins(10, 0, 8, 0)

            self._monitor_dot = QLabel("⬤ MONITORING OFF")

            self._monitor_dot.setStyleSheet(f"color:{self.C['text_muted']}; font-size:9px; font-weight:bold;")

            hrl.addWidget(self._monitor_dot)

            hrl.addWidget(QLabel(" │ "), 0)

            self._idx_status = QLabel("Not indexed")

            self._idx_status.setStyleSheet(f"color:{self.C['text_muted']}; font-size:9px;")

            hrl.addWidget(self._idx_status)

            hrl.addStretch()

            self._stats_label = QLabel("Files: —   Relations: —")

            self._stats_label.setStyleSheet(f"color:{self.C['text_muted']}; font-size:9px;")

            hrl.addWidget(self._stats_label)

            hrl.addWidget(QLabel(" "))

            clr = QToolButton(); clr.setText("Clear")

            clr.setStyleSheet(f"color:{self.C['text_muted']}; font-size:9px;")

            clr.clicked.connect(self._clear_stream)

            hrl.addWidget(clr)

            sl.addWidget(self._event_strip_hdr)

            self._event_stream = QTextEdit()

            self._event_stream.setReadOnly(True)

            self._event_stream.setStyleSheet(f"""

                QTextEdit {{ background:{self.C['bg_deep']}; border:none;

                    font-family:'Cascadia Code','Consolas',monospace;

                    font-size:10px; color:{self.C['text_sec']}; padding:2px 10px; }}

            """)

            sl.addWidget(self._event_stream)

            layout.addWidget(self._event_strip)

        # ── Project Root Detection & Auto-Indexing ───────────────────────

        def _find_project_root_for_path(self, path: Path) -> Optional[Path]:

            try:

                p = path.resolve()

            except Exception:

                p = path

            if p.is_file():

                p = p.parent

            if len(p.parts) <= 1 or p.parent == p:

                return None

            # Skip huge system/runtime directories from being auto-detected as code projects

            p_str_lower = str(p).lower()

            is_temp = "temp" in p_str_lower or "tmp" in p_str_lower

            skip_terms = ("windows", "program files", "program files (x86)", "system volume information", "$recycle.bin")

            if not is_temp and (any(term in p_str_lower for term in skip_terms) or "appdata" in p_str_lower or "local settings" in p_str_lower):

                return None

            # Check upward for common project root markers

            markers = {".git", "requirements.txt", "pyproject.toml", "setup.py", "package.json", "Pipfile", "poetry.lock"}

            curr = p

            best_root = None

            found_marker = False

            while len(curr.parts) > 1 and curr.parent != curr:

                for m in markers:

                    if (curr / m).exists():

                        best_root = curr

                        found_marker = True

                        break

                if found_marker:

                    break

                try:

                    with os.scandir(curr) as it:

                        for entry in it:

                            if entry.is_file() and entry.name.endswith(".py"):

                                best_root = curr

                                break

                except Exception:

                    pass

                curr = curr.parent

            return best_root

        def _auto_index_if_needed(self, path_str: str):

            if not path_str or path_str == "__DUMMY__":

                return

            try:

                p = Path(path_str).resolve()

            except Exception:

                return

            # Never scan a filesystem drive root (e.g. C:\ or D:\)

            if len(p.parts) <= 1 or p.parent == p:

                return

            # Check if current directory or file is already covered by the indexed project

            if (

                self._service.current_graph is not None and

                self._service.project_root is not None

            ):

                cur_proj_norm = os.path.normcase(os.path.abspath(str(self._service.project_root)))

                p_norm = os.path.normcase(os.path.abspath(str(p)))

                if p_norm == cur_proj_norm or p_norm.startswith(cur_proj_norm + os.sep):

                    return

            # If scan worker is currently running, skip

            if hasattr(self, "_scan_worker") and self._scan_worker is not None and self._scan_worker.isRunning():

                return

            # Find the best project root for this path

            proj_root = self._find_project_root_for_path(p)

            if not proj_root or len(proj_root.parts) <= 1 or proj_root.parent == proj_root:

                return

            # Check if this resolved project root is already indexed

            if (

                self._service.current_graph is not None and

                self._service.project_root is not None

            ):

                cur_proj_norm = os.path.normcase(os.path.abspath(str(self._service.project_root)))

                req_proj_norm = os.path.normcase(os.path.abspath(str(proj_root)))

                if cur_proj_norm == req_proj_norm:

                    return

            # Automatically launch background project indexing

            self._start_scan(str(proj_root))

        # ── Navigation ────────────────────────────────────────────────────

        def _navigate_to(self, path_str: str, push_history=True):

            if not path_str:

                return

            try:

                p = Path(path_str).resolve()

            except Exception:

                p = Path(path_str)

            if not p.exists():

                self._status.showMessage(f"Path not found: {path_str}")

                return

            target_dir = p if p.is_dir() else p.parent

            target_dir_str = str(target_dir)

            self._current_dir = target_dir_str

            if hasattr(self._service, "assistant"):

                self._service.assistant.set_navigation_path(target_dir_str)

            # Reset search filter when navigating so all files in new directory are visible

            if hasattr(self, "_search_box") and self._search_box.text():

                self._search_box.blockSignals(True)

                self._search_box.clear()

                self._search_box.blockSignals(False)

                self._fs_model.setNameFilters([])

                self._fs_model.setNameFilterDisables(False)

            self._path_bar.setText(str(p))

            self._addr_label.setText(target_dir_str)

            self._update_index_badge(target_dir_str)

            idx = self._fs_model.setRootPath(target_dir_str)

            if idx.isValid():

                self._file_view.setRootIndex(idx)

            else:

                idx = self._fs_model.index(target_dir_str)

                if idx.isValid():

                    self._file_view.setRootIndex(idx)

            self._center_tabs.setCurrentIndex(0)

            if not p.is_dir():

                file_idx = self._fs_model.index(str(p))

                if file_idx.isValid():

                    self._file_view.setCurrentIndex(file_idx)

                    self._file_view.scrollTo(file_idx)

                self._update_preview(str(p))

            if push_history:

                self._nav_history = self._nav_history[:self._nav_pos + 1]

                self._nav_history.append(str(p))

                self._nav_pos = len(self._nav_history) - 1

            self._status.showMessage(f"Browsing: {target_dir_str}")

            # Auto-index project automatically when user navigates

            self._auto_index_if_needed(target_dir_str)

        def _navigate_to_path(self):

            self._navigate_to(self._path_bar.text().strip())

        def _nav_back(self):

            if self._nav_pos > 0:

                self._nav_pos -= 1

                self._navigate_to(self._nav_history[self._nav_pos], push_history=False)

        def _nav_forward(self):

            if self._nav_pos < len(self._nav_history) - 1:

                self._nav_pos += 1

                self._navigate_to(self._nav_history[self._nav_pos], push_history=False)

        def _is_text_input_focused(self) -> bool:

            fw = QApplication.focusWidget()

            return bool(fw and isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)))

        def _nav_up(self):

            if self._is_text_input_focused():

                return

            cur = self._path_bar.text().strip() or (self._current_dir if hasattr(self, "_current_dir") else "")

            if not cur:

                return

            p = Path(cur)

            parent = str(p.parent)

            if parent and parent != cur:

                self._navigate_to(parent)

        def _refresh(self):

            cur = self._path_bar.text().strip() or (self._current_dir if hasattr(self, "_current_dir") else "")

            if cur:

                self._navigate_to(cur, push_history=False)

        def _open_folder_dialog(self):

            start = self._current_dir if (hasattr(self, "_current_dir") and self._current_dir) else str(Path.home())

            folder = QFileDialog.getExistingDirectory(self, "Select Folder to Open", start)

            if folder:

                self._navigate_to(folder)

                self._auto_index_if_needed(folder)

        def _index_current_folder(self):

            cur = self._current_dir or self._path_bar.text().strip()

            if cur and Path(cur).is_dir():

                p = Path(cur)

                # If current folder has no Python scripts, but parent does (and parent is not drive root)

                if p.parent != p and len(p.parent.parts) > 1 and not list(p.glob("*.py")) and list(p.parent.glob("*.py")):

                    reply = QMessageBox.question(

                        self, "Index Project Scope",

                        f"Current folder '{p.name}' appears to be a subfolder of '{p.parent.name}' (which contains project scripts).\n\n"

                        f"Would you like to index the entire project '{p.parent.name}' so all dependencies and datasets are mapped?",

                        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes

                    )

                    if reply == QMessageBox.Yes:

                        self._start_scan(str(p.parent))

                        return

                self._start_scan(cur)

        def _update_index_badge(self, dir_path: str):

            if not hasattr(self, "_idx_label"):

                return

            is_indexed = (

                self._service.current_graph is not None and

                self._service.project_root is not None and

                (

                    os.path.normcase(os.path.abspath(dir_path)) == os.path.normcase(os.path.abspath(str(self._service.project_root))) or

                    os.path.normcase(os.path.abspath(dir_path)).startswith(os.path.normcase(os.path.abspath(str(self._service.project_root))) + os.sep)

                )

            )

            if is_indexed:

                stats = self._service.get_graph_stats()

                self._idx_label.setText(f"✓ Indexed Project ({stats.get('nodes', 0)} files)")

                self._idx_label.setStyleSheet(f"color:{self.C['green']}; font-size:10px; font-weight:bold;")

                if hasattr(self, "_btn_index_now"):

                    self._btn_index_now.setText("⚡  Re-index Project")

            else:

                self._idx_label.setText("Folder View (Fast)")

                self._idx_label.setStyleSheet(f"color:{self.C['text_muted']}; font-size:10px;")

                if hasattr(self, "_btn_index_now"):

                    self._btn_index_now.setText("⚡  Index as Project")

        def _on_directory_loaded(self, path: str):

            if hasattr(self, "_current_dir") and self._current_dir:

                try:

                    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(self._current_dir)):

                        idx = self._fs_model.index(self._current_dir)

                        if idx.isValid():

                            self._file_view.setRootIndex(idx)

                            if self._selected_path and Path(self._selected_path).parent == Path(self._current_dir):

                                s_idx = self._fs_model.index(self._selected_path)

                                if s_idx.isValid():

                                    self._file_view.setCurrentIndex(s_idx)

                except Exception:

                    pass

        def _set_path_and_scan(self, path_str: str):

            self._navigate_to(path_str)

            self._start_scan(path_str)

        # ── Left tree clicks ──────────────────────────────────────────────

        def _on_left_tree_item(self, item: QTreeWidgetItem, col: int):

            path = item.data(0, Qt.UserRole)

            if path and path != "__DUMMY__":

                self._navigate_to(path)

                self._auto_index_if_needed(path)

            self._update_action_bar_state()

        # ── File clicks ───────────────────────────────────────────────────

        def _on_file_selection_changed(self, *args):

            sel_path = self._get_active_selected_path()

            if sel_path:

                self._selected_path = sel_path

                self._update_preview(sel_path)

                if self._ai_open:

                    b_stat = self._service.model_manager.get_status()

                    self._ai_ctx.setText(f"Context: {Path(sel_path).name}  |  AI: {b_stat['backend']} ({b_stat['accelerator']})")

                if self._service.current_graph and Path(sel_path).is_file():

                    self._start_impact_lookup(sel_path)

            self._update_action_bar_state()

        def _on_file_clicked(self, index: QModelIndex):
            path = self._fs_model.filePath(index)
            if path:
                self._selected_path = path
                self._update_preview(path)
                if hasattr(self._service, "assistant"):
                    self._service.assistant.context.set_target(path)
                if self._ai_open:
                    self._ai_ctx.setText(f"Context: {Path(path).name}")

        def _on_file_double_clicked(self, index: QModelIndex):
            path = self._fs_model.filePath(index)
            if not path:
                return
            p = Path(path)
            if p.is_dir():
                self._navigate_to(path)
            else:
                self._selected_path = path
                self._update_preview(path)
                try:
                    from PySide6.QtGui import QDesktopServices
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                except Exception:
                    pass

        # ── Context menu ──────────────────────────────────────────────────
        def _show_context_menu(self, pos):
            index = self._file_view.indexAt(pos)
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};
                         color:{self.C['text_pri']}; font-size:11px; padding:4px; }}
                QMenu::item {{ padding:5px 20px; border-radius:3px; }}
                QMenu::item:selected {{ background:{self.C['accent']}; color:#fff; }}
                QMenu::separator {{ height:1px; background:{self.C['border']}; margin:3px 0; }}
            """)

            def act(label, slot, shortcut=None, enabled=True):
                a = QAction(label, menu)
                a.setEnabled(enabled)
                a.triggered.connect(slot)
                if shortcut:
                    a.setShortcut(shortcut)
                menu.addAction(a)
                return a

            can_paste = bool(getattr(self, "_clipboard_path", None) and Path(self._clipboard_path).exists())
            if not can_paste:
                try:
                    c = QApplication.clipboard()
                    md = c.mimeData()
                    if md and md.hasUrls():
                        can_paste = True
                except Exception:
                    pass

            if index.isValid():
                self._file_view.setCurrentIndex(index)
                path = self._fs_model.filePath(index)
                self._selected_path = path
                p = Path(path)

                if p.is_dir():
                    act("📂  Open Folder\tEnter", lambda: self._navigate_to(path))
                else:
                    act("📂  Open\tEnter", lambda: self._open_file(path))
                act("🪟  Reveal in Windows Explorer", lambda: self._reveal_in_os_explorer(path))
                menu.addSeparator()

                act("✂️  Cut\tCtrl+X", lambda: self._cut_selection(path))
                act("📋  Copy\tCtrl+C", lambda: self._copy_selection(path))
                act("📥  Paste\tCtrl+V", self._paste_selection, enabled=can_paste)
                act("✏️  Rename…\tF2", lambda: self._rename_file(path))
                act("🗑️  Delete…\tDel", lambda: self._delete_file(path))
                menu.addSeparator()

                act("📦  Move to…", lambda: self._move_to_dialog(path))
                act("📂  Copy to…", lambda: self._copy_to_dialog(path))
                act("🔗  Copy as Path\tCtrl+Shift+C", lambda: self._copy_as_path(path))
                menu.addSeparator()

                # New Submenu
                new_sub = menu.addMenu("➕  New")
                new_sub.setStyleSheet(f"""
                    QMenu {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};
                             color:{self.C['text_pri']}; font-size:11px; padding:4px; }}
                    QMenu::item {{ padding:5px 20px; border-radius:3px; }}
                    QMenu::item:selected {{ background:{self.C['accent']}; color:#fff; }}
                """)
                a_fld = QAction("📁  Folder\tCtrl+Shift+N", new_sub)
                a_fld.triggered.connect(self._new_folder)
                new_sub.addAction(a_fld)

                a_doc = QAction("📄  Text Document", new_sub)
                a_doc.triggered.connect(lambda: self._new_file("New Document.txt"))
                new_sub.addAction(a_doc)

                a_py = QAction("🐍  Python Script", new_sub)
                a_py.triggered.connect(lambda: self._new_file("script.py"))
                new_sub.addAction(a_py)

                a_cfg = QAction("⚙️  Config File (.json)", new_sub)
                a_cfg.triggered.connect(lambda: self._new_file("config.json"))
                new_sub.addAction(a_cfg)
                menu.addSeparator()

                # PreView AI Power Actions
                if p.is_dir():
                    act("⚡  Index as Project", lambda: self._start_scan(path))
                act("⚡  Simulate Impact", lambda: self._show_impact_for(path))
                act("📊  Show in Dependency Graph", lambda: self._show_deps_for(path))
                act("✨  Ask PreView AI", lambda: self._ask_ai_about(path))
                menu.addSeparator()

                act("ℹ️  Properties\tAlt+Enter", lambda: self._show_properties(path))
            else:
                # Clicked on blank space in current directory
                cur_dir = str(self._get_current_directory())

                new_sub = menu.addMenu("➕  New")
                new_sub.setStyleSheet(f"""
                    QMenu {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};
                             color:{self.C['text_pri']}; font-size:11px; padding:4px; }}
                    QMenu::item {{ padding:5px 20px; border-radius:3px; }}
                    QMenu::item:selected {{ background:{self.C['accent']}; color:#fff; }}
                """)
                a_fld = QAction("📁  Folder\tCtrl+Shift+N", new_sub)
                a_fld.triggered.connect(self._new_folder)
                new_sub.addAction(a_fld)

                a_doc = QAction("📄  Text Document", new_sub)
                a_doc.triggered.connect(lambda: self._new_file("New Document.txt"))
                new_sub.addAction(a_doc)

                a_py = QAction("🐍  Python Script", new_sub)
                a_py.triggered.connect(lambda: self._new_file("script.py"))
                new_sub.addAction(a_py)

                a_cfg = QAction("⚙️  Config File (.json)", new_sub)
                a_cfg.triggered.connect(lambda: self._new_file("config.json"))
                new_sub.addAction(a_cfg)
                menu.addSeparator()

                act("📥  Paste\tCtrl+V", self._paste_selection, enabled=can_paste)
                menu.addSeparator()

                act("⚡  Index Current Folder as Project", self._index_current_folder)
                act("🔄  Refresh\tF5", self._refresh)
                act("🪟  Open in Windows Explorer", lambda: self._reveal_in_os_explorer(cur_dir))
                menu.addSeparator()
                act("ℹ️  Folder Properties\tAlt+Enter", lambda: self._show_properties(cur_dir))

            global_pos = self._file_view.viewport().mapToGlobal(pos) if pos is not None else QCursor.pos()
            menu.exec(global_pos)

        # ── Scanning ──────────────────────────────────────────────────────

        def _start_scan(self, path_str: str):

            p = Path(path_str).resolve()

            if len(p.parts) <= 1 or p.parent == p:

                QMessageBox.warning(self, "Invalid Project Scope", "Cannot index an entire filesystem drive root as a project. Please select a specific project directory.")

                return

            if hasattr(self, "_scan_worker") and self._scan_worker is not None and self._scan_worker.isRunning():

                if hasattr(self._scan_worker, "path") and str(self._scan_worker.path) == str(p):

                    return

                try:

                    self._scan_worker.finished.disconnect()

                    self._scan_worker.progress.disconnect()

                except Exception:

                    pass

            self._sim_btn.setEnabled(False)

            self._exec_btn.setEnabled(False)

            self._progress.show()

            self._idx_status.setText("Indexing…")

            self._log_stream(f"Indexing project: {path_str}")

            self._status.showMessage(f"Indexing {path_str}…")

            self._scan_worker = ScanWorker(self._service, path_str)

            self._scan_worker.progress.connect(lambda m: self._log_stream(m))

            self._scan_worker.finished.connect(self._on_scan_done)

            self._scan_worker.start()

        def _on_scan_done(self, ok: bool, msg: str):

            self._progress.hide()

            self._sim_btn.setEnabled(True)

            if ok and self._service.current_graph:

                stats = self._service.get_graph_stats()

                self._stats_label.setText(

                    f"Files: {stats['nodes']}   Relations: {stats['edges']}"

                )

                self._idx_status.setText(

                    f"✓ Indexed  ({stats['nodes']} files, {stats['edges']} relations)"

                )

                self._log_stream(

                    f"✓ Project indexed — {stats['nodes']} files, {stats['edges']} relationships"

                )

                self._status.showMessage(

                    f"{self._service.project_root.name} — {stats['nodes']} files, {stats['edges']} relations"

                )

                self._update_graph_tab()

                self._populate_left_tree()

                # Update address bar badge

                if hasattr(self, "_current_dir") and self._current_dir:

                    self._update_index_badge(self._current_dir)

                # Auto-start watcher

                if not self._service.watcher_active:

                    self._start_watcher()

                # Trigger impact lookup for currently selected file now that index is ready

                if self._selected_path and Path(self._selected_path).is_file():

                    self._start_impact_lookup(self._selected_path)

                # Resume pending simulation if requested

                if hasattr(self, "_pending_sim_intent") and self._pending_sim_intent:

                    pending = self._pending_sim_intent

                    self._pending_sim_intent = None

                    self._intent_edit.setText(pending)

                    self._run_simulation()

            else:

                self._idx_status.setText("⚠ Indexing failed")

                self._log_stream(f"ERROR: {msg}")

                self._status.showMessage(f"Scan failed: {msg}")

        # ── Watcher ───────────────────────────────────────────────────────

        def _start_watcher(self):

            def on_change(event: ChangeEvent, impact: ImpactResult):

                self.fs_change_signal.emit(event, impact)

            ok = self._service.start_watcher(on_change)

            if ok:

                self._monitor_dot.setText("⬤ MONITORING ON")

                self._monitor_dot.setStyleSheet(

                    f"color:{C['green']}; font-size:9px; font-weight:bold;"

                )

                self._log_stream(f"⬤ Filesystem watcher started: {self._service.project_root}")

            else:

                self._log_stream("⚠ Filesystem watcher unavailable (install watchdog)")

        @Slot(object, object)

        def _on_fs_change_ui(self, event: ChangeEvent, impact: ImpactResult):

            pn = Path(event.path).name

            on = Path(event.old_path).name if event.old_path else None

            ev  = event.event_type.value

            desc = f"{ev}: {on} → {pn}" if on else f"{ev}: {pn}"

            self._log_stream(f"[USER MADE] {desc}")

            self._log_stream(

                f"  ↳ Risk: {impact.risk.value}  |  {impact.confirmed_count} confirmed affected"

            )

            if impact.affected_files:

                self._log_stream(

                    f"  ↳ Affected: {', '.join(f.name for f in impact.affected_files[:5])}"

                )

            self._current_impact = impact

            self._show_change_notification(desc, impact)

            self._update_preview_impact(impact)

            self._update_graph_tab()

            # Refresh file view

            self._file_view.viewport().update()


        def _show_change_notification(self, desc: str, impact: ImpactResult):

            risk_color = RISK_C.get(impact.risk.value, C["text_sec"])

            n_aff = len(impact.affected_files)

            body = f"<b style='color:{risk_color};'>Change detected</b><br>"

            body += f"{desc}<br>"

            if n_aff:

                body += f"<span style='color:{C['yellow']};'>{n_aff} dependent file{'s' if n_aff!=1 else ''} may be affected</span>"

            else:

                body += f"<span style='color:{C['green']};'>No confirmed dependents</span>"

            self._status.showMessage(f"Change: {desc} → Risk: {impact.risk.value}")

        # ── Preview panel (Section 12: Killer Impact Panel) ─────────────────

        def _update_preview(self, path_str: str):

            p = Path(path_str)

            if not p.exists():

                return

            try:

                stat = p.stat()

                size = stat.st_size

                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

            except OSError:

                size, mtime = 0, "—"

            ext = p.suffix.lower()

            icon = _file_icon(ext)

            kind = _file_kind(ext)

            # Compute dependencies from current project graph

            used_by_names = []

            depends_on_names = []

            if self._service.current_graph:

                g = self._service.current_graph

                # Incoming: files that use/depend on this file

                for _, node in g.get_dependents(str(p)):

                    if node.name not in used_by_names and node.name != p.name:

                        used_by_names.append(node.name)

                for _, node in g.get_dependents(p.name):

                    if node.name not in used_by_names and node.name != p.name:

                        used_by_names.append(node.name)

                # Outgoing: files that this file depends on

                for _, node in g.get_dependencies(str(p)):

                    if node.name not in depends_on_names and node.name != p.name:

                        depends_on_names.append(node.name)

                for _, node in g.get_dependencies(p.name):

                    if node.name not in depends_on_names and node.name != p.name:

                        depends_on_names.append(node.name)

            used_by_rows = "".join([f"<div style='color:{C['yellow']}; padding:1px 0;'>• {name}</div>" for name in used_by_names]) if used_by_names else f"<div style='color:{C['text_muted']}; font-style:italic;'>None detected</div>"

            depends_on_rows = "".join([f"<div style='color:{C['cyan']}; padding:1px 0;'>• {name}</div>" for name in depends_on_names]) if depends_on_names else f"<div style='color:{C['text_muted']}; font-style:italic;'>None detected</div>"

            html = f"""

            <div style='font-family:Segoe UI,sans-serif; color:{C['text_sec']}; padding:2px;'>

              <div style='font-size:10px; font-weight:800; color:{C['accent']}; letter-spacing:0.8px; margin-bottom:4px;'>

                FILE INFORMATION

              </div>

              <div style='font-size:13px; font-weight:700; color:{C['text_pri']}; margin-bottom:6px;'>

                {icon} {p.name}

              </div>

              <table style='font-size:11px; line-height:1.6; width:100%; margin-bottom:8px;'>

                <tr><td style='color:{C['text_muted']}; width:55px;'>Type</td>

                    <td style='color:{C['text_pri']};'>{kind}</td></tr>

                <tr><td style='color:{C['text_muted']};'>Size</td>

                    <td style='color:{C['text_pri']};'>{_format_size(size)}</td></tr>

                <tr><td style='color:{C['text_muted']};'>Modified</td>

                    <td style='color:{C['text_pri']};'>{mtime}</td></tr>

                <tr><td style='color:{C['text_muted']};'>Path</td>

                    <td style='color:{C['text_muted']}; font-size:10px; word-break:break-all;'>{str(p)}</td></tr>

              </table>

              <div style='border-top:1px solid {C['border']}; padding-top:6px; margin-top:4px;'>

                <div style='font-size:10px; font-weight:800; color:{C['accent']}; letter-spacing:0.8px; margin-bottom:4px;'>

                  DEPENDENCIES

                </div>

                <div style='font-size:11px; font-weight:bold; color:{C['text_pri']}; margin-bottom:2px;'>Used by:</div>

                <div style='font-size:11px; margin-left:8px; margin-bottom:6px;'>{used_by_rows}</div>

                <div style='font-size:11px; font-weight:bold; color:{C['text_pri']}; margin-bottom:2px;'>Depends on:</div>

                <div style='font-size:11px; margin-left:8px;'>{depends_on_rows}</div>

              </div>

            </div>

            """

            self._preview_info.setHtml(html)

            self._preview_impact.setPlaceholderText("Analyzing impact…")

            # Check cache

            cached = self._impact_cache.get(path_str)

            if cached:

                self._update_preview_impact(cached)

        def _start_impact_lookup(self, path_str: str):

            self._impact_worker = ImpactWorker(self._service, path_str, "DELETE")

            self._impact_worker.finished.connect(self._on_impact_ready)

            self._impact_worker.start()

        @Slot(object)

        def _on_impact_ready(self, impact: Optional[ImpactResult]):

            if impact and self._selected_path:

                self._impact_cache[self._selected_path] = impact

                self._update_preview_impact(impact)

        def _update_preview_impact(self, impact: ImpactResult):

            risk_color = RISK_C.get(impact.risk.value, C["text_sec"])

            n_aff = len(impact.affected_files)

            n_ds  = len(impact.downstream_files)

            b_stat = self._service.model_manager.get_status()

            ai_timing_badge = f"<span style='color:{C['accent']}; font-size:9px; font-weight:bold;'>⚡ {b_stat['backend']} ({b_stat['accelerator']}) • {impact.analysis_time_ms:.1f}ms • Offline</span>"

            if impact.affected_files:

                top_aff = impact.affected_files[0]

                reason_str = f"Referenced by {top_aff.name} ({top_aff.relationship or 'dependency'})."

            elif not impact.analysis_complete:

                reason_str = impact.summary or "Analysis incomplete."

            else:

                reason_str = "No active downstream dependencies detected."

            rows = ""

            for f in impact.affected_files[:8]:

                conf_c = {"CONFIRMED": C["green"], "LIKELY": C["cyan"],

                          "POSSIBLE": C["yellow"], "UNCERTAIN": C["text_muted"]

                         }.get(f.confidence.value, C["text_sec"])

                rows += f"""

                <tr>

                  <td style='padding:3px 6px; color:{C['yellow']}; font-weight:bold;'>{f.name}</td>

                  <td style='padding:3px 6px; color:{conf_c}; font-size:10px;'>{f.confidence.value}</td>

                  <td style='padding:3px 6px; color:{C['text_muted']}; font-size:10px;'>{f.relationship}</td>

                </tr>"""

            if n_aff > 8:

                rows += f"<tr><td colspan=3 style='padding:3px 6px; color:{C['text_muted']}; font-size:10px;'>… {n_aff-8} more</td></tr>"

            table_part = f"""

              <table style='width:100%; border-collapse:collapse; margin-top:8px;'>

                <tr style='background:{C['bg_card']};'>

                  <th style='padding:3px 6px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>FILE</th>

                  <th style='padding:3px 6px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>CONF.</th>

                  <th style='padding:3px 6px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>HOW</th>

                </tr>

                {rows}

              </table>

            """ if rows else ""

            html = f"""

            <div style='font-family:Segoe UI,sans-serif;'>

              <div style='font-size:10px; font-weight:800; color:{C['accent']}; letter-spacing:0.8px; margin-bottom:6px;'>

                IMPACT

              </div>

              <table style='font-size:11px; line-height:1.7; width:100%; margin-bottom:6px;'>

                <tr>

                  <td style='color:{C['text_muted']}; width:125px;'>Potentially affected:</td>

                  <td style='color:{C['text_pri']}; font-weight:bold;'>{n_aff} file{'s' if n_aff!=1 else ''}{f' (+ {n_ds} downstream)' if n_ds else ''}</td>

                </tr>

                <tr>

                  <td style='color:{C['text_muted']};'>Risk:</td>

                  <td><span style='font-size:12px; font-weight:800; color:{risk_color}; letter-spacing:0.5px;'>{impact.risk.value}</span></td>

                </tr>

                <tr>

                  <td style='color:{C['text_muted']}; vertical-align:top;'>Reason:</td>

                  <td style='color:{C['text_pri']}; font-size:11px;'>{reason_str}</td>

                </tr>

              </table>

              <div style='margin-top:6px; margin-bottom:4px;'>{ai_timing_badge}</div>

              {table_part}

            </div>"""

            self._preview_impact.setHtml(html)

        # ── Simulation ────────────────────────────────────────────────────

        def _run_simulation(self):

            intent = self._intent_edit.text().strip()

            if not intent:

                QMessageBox.warning(self, "Input Required", "Please enter a proposed action.")

                return

            # If project is not yet indexed, try auto-detecting the enclosing project

            if not self._service.current_graph:

                cur = getattr(self, "_current_dir", "") or self._path_bar.text().strip()

                cand = Path(cur) if cur and Path(cur).exists() else None

                project_cand = None

                if cand:

                    check = cand if cand.is_dir() else cand.parent

                    for ancestor in [check] + list(check.parents):

                        if list(ancestor.glob("*.py")) or (ancestor / "requirements.txt").exists() or (ancestor / ".git").exists():

                            project_cand = ancestor

                            break

                    if not project_cand and cand.is_dir():

                        project_cand = cand

                if project_cand:

                    self._pending_sim_intent = intent

                    self._log_stream(f"Auto-indexing project for simulation: {project_cand.name}")

                    self._start_scan(str(project_cand))

                    return

                QMessageBox.warning(self, "No Project", "Please open or index a project folder first.")

                return

            # If current graph was indexed on a subfolder (like dataset/) whose parent has project files

            # or if the user is simulating deleting the very folder that was indexed

            proj_root = self._service.project_root

            if proj_root and proj_root.parent and proj_root.parent != proj_root and len(proj_root.parent.parts) > 1:

                parent_has_py = any(proj_root.parent.glob("*.py"))

                intent_targets_root = proj_root.name.lower() in intent.lower()

                no_py_in_root = not any(proj_root.glob("*.py"))

                if (intent_targets_root or no_py_in_root) and parent_has_py:

                    self._pending_sim_intent = intent

                    self._log_stream(f"Expanding project scope to enclosing project: {proj_root.parent.name}")

                    self._start_scan(str(proj_root.parent))

                    return

            self._sim_btn.setEnabled(False)

            self._exec_btn.setEnabled(False)

            self._cancel_btn.setEnabled(False)

            self._progress.show()

            self._sim_result.clear()

            self._log_stream(f"Simulation: {intent}")

            self._status.showMessage("Simulating…")

            self._center_tabs.setCurrentIndex(2)

            self._sim_worker = SimWorker(self._service, intent)

            self._sim_worker.finished.connect(self._on_sim_done)

            self._sim_worker.start()

        def _on_sim_done(self, ok: bool, msg: str, data: dict):

            self._progress.hide()

            self._sim_btn.setEnabled(True)

            if not ok:

                self._sim_result.setHtml(f"""

                <div style='font-family:Segoe UI,sans-serif; color:{C['red']};

                            font-size:14px; font-weight:bold; padding:16px;'>

                  ⛔ BLOCKED<br>

                  <span style='font-size:12px; color:{C['text_sec']};'>{msg}</span>

                </div>""")

                self._log_stream(f"BLOCKED: {msg}")

                return

            impact: ImpactResult = data.get("impact")

            action = data.get("action")

            explanation = data.get("explanation", "")

            self._current_impact = impact

            self._render_sim_result(impact, action, explanation)

            self._exec_btn.setEnabled(True)

            self._cancel_btn.setEnabled(True)

            risk_color = RISK_C.get(impact.risk.value, C["text_sec"])

            self._log_stream(

                f"✓ Simulation done — Risk: {impact.risk.value}, "

                f"{impact.confirmed_count} confirmed, {impact.total_affected} total"

            )

            self._status.showMessage(

                f"Simulation: {action.operation} {action.target} → "

                f"Risk {impact.risk.value}, {impact.confirmed_count} confirmed"

            )

        def _render_sim_result(self, impact: ImpactResult, action, explanation: str):

            risk_val   = impact.risk.value

            risk_color = RISK_C.get(risk_val, C["text_sec"])

            dest_str   = f" → {Path(impact.destination).name}" if impact.destination else ""

            rows_html = ""

            for i, f in enumerate(impact.affected_files, 1):

                conf_c = {"CONFIRMED": C["green"], "LIKELY": C["cyan"],

                          "POSSIBLE": C["yellow"], "UNCERTAIN": C["text_muted"]

                         }.get(f.confidence.value, C["text_sec"])

                rows_html += f"""

                <tr style='border-bottom:1px solid {C['border']};'>

                  <td style='padding:7px 10px; color:{C['yellow']};'>{i}. {f.name}</td>

                  <td style='padding:7px 10px; color:{C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                  <td style='padding:7px 10px; color:{conf_c}; font-size:10px;'>{f.confidence.value}</td>

                  <td style='padding:7px 10px; color:{C['text_muted']}; font-size:10px;'>{f.evidence_summary}</td>

                </tr>"""

            env_deps = getattr(impact, "environment_dependencies", [])

            env_section_html = ""

            if env_deps:

                env_rows = ""

                for i, f in enumerate(env_deps, 1):

                    env_rows += f"""

                    <tr style='border-bottom:1px solid {C['border']};'>

                      <td style='padding:7px 10px; color:{C['yellow']};'>{i}. {f.name}</td>

                      <td style='padding:7px 10px; color:{C['text_sec']}; font-size:10px;'>{f.relationship}</td>

                      <td style='padding:7px 10px; color:{C['green']}; font-size:10px;'>{f.confidence.value}</td>

                      <td style='padding:7px 10px; color:{C['text_muted']}; font-size:10px;'>{f.evidence_summary}</td>

                    </tr>"""

                env_section_html = f"""

                <div style='background:{C['bg_card']}; border:1px solid {C['border']};

                            border-radius:6px; margin-bottom:10px;'>

                  <div style='padding:7px 10px; border-bottom:1px solid {C['border']};'>

                    <span style='color:{C['text_muted']}; font-size:9px; font-weight:bold; letter-spacing:1px;'>

                      ENVIRONMENT DEPENDENCIES

                    </span>

                    &nbsp;

                    <span style='color:{C['yellow']}; font-size:11px; font-weight:bold;'>

                      {len(env_deps)} reference{'s' if len(env_deps)!=1 else ''}

                    </span>

                  </div>

                  <table style='width:100%; border-collapse:collapse;'>

                    <tr style='background:{C['bg_input']};'>

                      <th style='padding:5px 10px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>VARIABLE & SOURCE</th>

                      <th style='padding:5px 10px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>CATEGORY</th>

                      <th style='padding:5px 10px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>CONFIDENCE</th>

                      <th style='padding:5px 10px; text-align:left; color:{C['text_muted']}; font-size:9px; font-weight:bold;'>EVIDENCE & WHY</th>

                    </tr>

                    {env_rows}

                  </table>

                </div>"""

            no_impact = ""

            has_any_deps = bool(impact.affected_files or env_deps)

            if not has_any_deps and impact.analysis_complete:

                no_impact = f"""

                <div style='color:{C['green']}; padding:10px; background:{C['bg_card']};

                            border-radius:5px; border:1px solid {C['border']}; margin-bottom:10px;'>

                  ✓ No confirmed dependent files or environment references found.<br>

                  <span style='font-size:10px; color:{C['text_muted']};'>This change appears safe.</span>

                </div>"""

            elif not impact.analysis_complete:

                no_impact = f"""

                <div style='color:{C['orange']}; padding:10px; background:{C['bg_card']};

                            border-radius:5px; border:1px solid {C['border']}; margin-bottom:10px;'>

                  ⚠ ANALYSIS INCOMPLETE — {impact.summary}

                </div>"""

            ds_html = ""

            for f in impact.downstream_files:

                ds_html += f"<div style='color:{C['orange']}; font-size:11px;'>↳ {f.name} — {f.description}</div>"

            html = f"""

            <div style='font-family:Segoe UI,sans-serif; color:{C['text_pri']}; padding:4px;'>

              <div style='margin-bottom:14px;'>

                <span style='font-size:18px; font-weight:800; color:{risk_color};

                             letter-spacing:2px;'>{risk_val}</span>

                &nbsp;&nbsp;

                <span style='background:{C['bg_card']}; border:1px solid {C['border']};

                             padding:2px 8px; border-radius:3px; font-size:10px;

                             color:{C['text_muted']};'>AI PROPOSED</span>

              </div>

              <div style='background:{C['bg_card']}; border:1px solid {C['border']};

                          border-radius:6px; padding:10px; margin-bottom:10px;'>

                <div style='color:{C['text_muted']}; font-size:9px; font-weight:bold;

                            letter-spacing:1px; margin-bottom:5px;'>WHAT CHANGES</div>

                <span style='color:{risk_color}; font-weight:700;'>{impact.operation}</span>

                &nbsp;

                <code style='background:{C['bg_input']}; padding:1px 7px; border-radius:3px;

                             color:{C['cyan']};'>{impact.changed_object}{dest_str}</code>

              </div>

              {f'''

              <div style='background:{C['bg_card']}; border:1px solid {C['border']};

                          border-radius:6px; margin-bottom:10px;'>

                <div style='padding:7px 10px; border-bottom:1px solid {C['border']};'>

                  <span style='color:{C['text_muted']}; font-size:9px; font-weight:bold; letter-spacing:1px;'>

                    WHAT IS AFFECTED

                  </span>

                  &nbsp;

                  <span style='color:{C['yellow']}; font-size:11px; font-weight:bold;'>

                    {len(impact.affected_files)} file{"s" if len(impact.affected_files)!=1 else ""}

                  </span>

                </div>

                <table style='width:100%; border-collapse:collapse;'>

                  <tr style='background:{C['bg_input']};'>

                    <th style='padding:5px 10px; text-align:left; color:{C['text_muted']};

                               font-size:9px; font-weight:bold;'>FILE</th>

                    <th style='padding:5px 10px; text-align:left; color:{C['text_muted']};

                               font-size:9px; font-weight:bold;'>HOW</th>

                    <th style='padding:5px 10px; text-align:left; color:{C['text_muted']};

                               font-size:9px; font-weight:bold;'>CONFIDENCE</th>

                    <th style='padding:5px 10px; text-align:left; color:{C['text_muted']};

                               font-size:9px; font-weight:bold;'>EVIDENCE</th>

                  </tr>

                  {rows_html}

                </table>

              </div>''' if impact.affected_files else no_impact}

              {env_section_html}

              {no_impact if not has_any_deps else ""}

              {f'<div style="margin-bottom:10px;">{ds_html}</div>' if ds_html else ""}

              <div style='background:{C['bg_card']}; border:1px solid {C['border']};

                          border-radius:6px; padding:10px;'>

                <div style='color:{C['text_muted']}; font-size:9px; font-weight:bold;

                            letter-spacing:1px; margin-bottom:5px;'>EXPLANATION</div>

                <div style='color:{C['text_sec']}; font-size:11px; line-height:1.7;'>

                  {explanation.replace(chr(10),'<br>')}

                </div>

              </div>

            </div>"""

            self._sim_result.setHtml(html)

        def _cancel_sim(self):

            self._exec_btn.setEnabled(False)

            self._cancel_btn.setEnabled(False)

            self._sim_result.clear()

            self._log_stream("Simulation cancelled.")

        def _execute_action(self):

            if not self._service.last_action:

                return

            action = self._service.last_action

            dest_line = f"\nDestination: {action.destination}" if action.destination else ""

            reply = QMessageBox.question(

                self, "Confirm Execution",

                f"Execute this action on the REAL filesystem?\n\n"

                f"Operation: {action.operation}\n"

                f"Target: {action.target}"

                f"{dest_line}",

                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,

            )

            if reply != QMessageBox.Yes:

                self._record_operation_history(str(action.operation), str(action.target), str(action.destination or ""), "Cancelled", "User cancelled")

                return

            self._exec_btn.setEnabled(False)

            self._cancel_btn.setEnabled(False)

            self._progress.show()

            ok, msg, data = self._service.execute_and_verify()

            self._progress.hide()

            ver = data.get("verification")

            ver_status = ver.status if ver else "N/A"

            self._log_stream(f"Executed: {msg} | Verification: {ver_status}")

            self._status.showMessage(f"Executed — {ver_status}")

            self._update_graph_tab()

        # ── AI Panel ──────────────────────────────────────────────────────

        def _toggle_ai_panel(self):

            self._ai_open = self._ai_btn.isChecked()

            if self._ai_open:

                # If floating window exists and is open, raise it

                if hasattr(self, "_ai_floating_window") and self._ai_floating_window and self._ai_floating_window.isVisible():

                    self._ai_floating_window.raise_()

                    self._ai_floating_window.activateWindow()

                    self._ai_input.setFocus()

                    return

                self._right_stack.setCurrentIndex(1)

                if self._selected_path:

                    self._ai_ctx.setText(f"Context: {Path(self._selected_path).name}")

                self._ai_input.setFocus()

                sizes = self._main_splitter.sizes()

                if len(sizes) >= 3 and sizes[2] < 120:

                    target = 360

                    center_w = max(200, sizes[1] - (target - sizes[2]))

                    self._main_splitter.setSizes([sizes[0], center_w, target])

            else:

                if hasattr(self, "_ai_floating_window") and self._ai_floating_window and self._ai_floating_window.isVisible():

                    self._ai_floating_window.hide()

                self._right_stack.setCurrentIndex(0)

        def _close_ai_panel(self):

            self._ai_btn.setChecked(False)

            self._toggle_ai_panel()

        def _toggle_ai_floating(self):

            """Toggle AI panel between docked in right stack and floating movable window."""

            if not hasattr(self, "_ai_floating_window") or self._ai_floating_window is None:

                self._ai_floating_window = QDialog(self, Qt.Window)

                self._ai_floating_window.setWindowTitle("✨ PreView AI Assistant")

                self._ai_floating_window.resize(420, 680)

                self._ai_floating_window.setStyleSheet(f"background:{self.C['bg_deep']}; color:{self.C['text_pri']};")

                fl = QVBoxLayout(self._ai_floating_window)

                fl.setContentsMargins(0, 0, 0, 0)

                self._ai_floating_layout = fl

                def _on_float_close(event):

                    self._dock_ai_panel()

                    event.accept()

                self._ai_floating_window.closeEvent = _on_float_close

            if self._ai_page_widget.parent() != self._ai_floating_window:

                # Detach and move to floating window

                self._ai_page_widget.setParent(self._ai_floating_window)

                self._ai_floating_layout.addWidget(self._ai_page_widget)

                self._ai_popout_btn.setText("↙")

                self._ai_popout_btn.setToolTip("Dock back to main window")

                self._right_stack.setCurrentIndex(0)

                self._ai_floating_window.show()

                self._ai_floating_window.raise_()

                self._ai_floating_window.activateWindow()

                self._ai_input.setFocus()

            else:

                self._dock_ai_panel()

        def _dock_ai_panel(self):

            """Dock AI panel back into right stack."""

            if hasattr(self, "_ai_page_widget") and hasattr(self, "_right_stack"):

                if self._ai_page_widget.parent() != self._right_stack:

                    self._ai_page_widget.setParent(self._right_stack)

                    self._right_stack.insertWidget(1, self._ai_page_widget)

                    self._ai_popout_btn.setText("⧉")

                    self._ai_popout_btn.setToolTip("Detach / Pop out AI panel into a movable, floating window")

                    if hasattr(self, "_ai_floating_window") and self._ai_floating_window and self._ai_floating_window.isVisible():

                        self._ai_floating_window.hide()

                    if self._ai_open:

                        self._right_stack.setCurrentIndex(1)

                        self._ai_input.setFocus()

        def _update_ai_status_badge(self):

            if not hasattr(self, "_ai_status_badge"):

                return

            b_status = self._service.model_manager.get_status()

            is_npu = b_status.get("is_npu", False)

            backend_name = b_status.get("backend", "ONNX Runtime")

            accel = b_status.get("accelerator", "CPU")

            last_inf = b_status.get("last_inference_time_ms", 0.0)

            if is_npu:

                badge_text = f"● QNN • {accel}"

                badge_style = """

                    QToolButton {

                        color: #6ee7b7; background: rgba(5, 150, 105, 0.25);

                        border: 1px solid #10b981; border-radius: 9px;

                        font-size: 10px; font-weight: 700; padding: 2px 7px;

                    }

                    QToolButton:hover { background: rgba(5, 150, 105, 0.40); }

                """

            else:

                badge_text = f"● {backend_name} • {accel}"

                badge_style = """

                    QToolButton {

                        color: #93c5fd; background: rgba(37, 99, 235, 0.20);

                        border: 1px solid #3b82f6; border-radius: 9px;

                        font-size: 10px; font-weight: 600; padding: 2px 7px;

                    }

                    QToolButton:hover { background: rgba(37, 99, 235, 0.35); }

                """

            self._ai_status_badge.setText(badge_text)

            self._ai_status_badge.setStyleSheet(badge_style)

        def _show_ai_diagnostics(self):

            diag_text = self._service.model_manager.format_diagnostics()

            dlg = QDialog(self)

            dlg.setWindowTitle("Snapdragon AI Diagnostics & Performance")

            dlg.resize(480, 430)

            dlg.setStyleSheet(f"background:{self.C['bg_deep']}; color:{self.C['text_pri']};")

            dl = QVBoxLayout(dlg)

            dl.setContentsMargins(16, 16, 16, 16)

            dl.setSpacing(10)

            hdr = QLabel("⚡ Snapdragon & On-Device AI Diagnostics")

            hdr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{self.C['accent']};")

            dl.addWidget(hdr)

            txt = QTextEdit()

            txt.setReadOnly(True)

            txt.setStyleSheet(f"""

                QTextEdit {{

                    background:{self.C['bg_card']}; border:1px solid {self.C['border']};

                    border-radius:6px; font-family:'Cascadia Code','Consolas',monospace;

                    font-size:11px; color:{self.C['text_pri']}; padding:10px; line-height:1.5;

                }}

            """)

            txt.setPlainText(diag_text)

            dl.addWidget(txt, stretch=1)

            close_btn = QPushButton("Close")

            close_btn.setFixedHeight(30)

            close_btn.setStyleSheet(f"""

                QPushButton {{ background:{self.C['bg_card']}; border:1px solid {self.C['border']};

                    color:{self.C['text_sec']}; font-weight:bold; border-radius:4px; }}

                QPushButton:hover {{ border-color:{self.C['accent']}; color:{self.C['text_pri']}; }}

            """)

            close_btn.clicked.connect(dlg.accept)

            dl.addWidget(close_btn)

            dlg.exec()

        def _send_ai_message(self):

            msg = self._ai_input.text().strip()

            if not msg:

                return

            self._ai_input.clear()

            self._append_ai_chat("You", msg, C["text_pri"])

            self._handle_ai_query(msg)

        def _on_quick_prompt(self):

            btn: QPushButton = self.sender()

            template = btn.property("prompt_template")

            fname = Path(self._selected_path).name if self._selected_path else "this file"

            prompt = template.replace("{file}", fname)

            self._ai_input.setText(prompt)

            self._send_ai_message()

        def _on_ai_confirm_action(self):

            if hasattr(self, "_ai_confirm_bar"):

                self._ai_confirm_bar.setVisible(False)

            self._append_ai_chat("You", "Confirm", self.C["text_pri"])

            self._handle_ai_query("confirm")

        def _on_ai_cancel_action(self):

            if hasattr(self, "_ai_confirm_bar"):

                self._ai_confirm_bar.setVisible(False)

            self._record_operation_history("AI_OPERATION", self._selected_path or "selected file", "", "Cancelled", "User cancelled proposal")

            self._append_ai_chat("You", "Cancel", self.C["text_pri"])

            self._handle_ai_query("cancel")

        def _ask_ai_about(self, path_str: str):

            self._selected_path = path_str

            self._ai_btn.setChecked(True)

            self._toggle_ai_panel()

            fname = Path(path_str).name

            self._ai_ctx.setText(f"Context: {fname}")

            if hasattr(self._service, "assistant"):

                self._service.assistant.context.set_target(path_str)

            self._append_ai_chat("System",

                f"File selected: {fname}\nAsk anything about this file…", C["text_muted"])

        def _handle_ai_query(self, query: str):

            """Process a query through the File Explorer-Wide AI Assistant."""

            query_str = query.strip()

            if not query_str:

                return

            # Hide confirmation bar if active

            if hasattr(self, "_ai_confirm_bar"):

                self._ai_confirm_bar.setVisible(False)

            # Update assistant's navigation location & selected context

            if self._current_dir:

                self._service.assistant.set_navigation_path(self._current_dir)

            if self._selected_path:

                self._service.assistant.context.set_target(self._selected_path)

            response = self._service.assistant.process_message(query_str)

            # Navigation / Selection in File Explorer UI

            if response.action_type in ("NAVIGATE", "SELECT"):

                if response.navigation_target:

                    self._navigate_to(response.navigation_target)

                if response.selected_target:

                    self._selected_path = response.selected_target

                    self._update_preview(response.selected_target)

                    f_idx = self._fs_model.index(response.selected_target)

                    if f_idx.isValid():

                        self._file_view.setCurrentIndex(f_idx)

                        self._file_view.scrollTo(f_idx)

            # Confirmation requirement: Show [Cancel] [Confirm] interactive bar

            if response.action_type == "PLAN_CONFIRMATION":

                if hasattr(self, "_ai_confirm_bar"):

                    self._ai_confirm_bar.setVisible(True)

            # Operation done: refresh views & update action bar

            if response.action_type == "OPERATION_DONE":

                self._update_action_bar_state()

                if self._current_dir:

                    self._fs_model.setRootPath(self._current_dir)

                if self._selected_path and Path(self._selected_path).exists():

                    self._update_preview(self._selected_path)

            # Synchronization with Simulate tab if simulation was triggered

            if (self._service.last_impact and hasattr(self, "_render_sim_result")

                    and hasattr(self, "_intent_edit") and self._service.last_action):

                self._current_impact = self._service.last_impact

                self._intent_edit.setText(self._service.last_action.raw_intent)

                self._render_sim_result(self._service.last_impact, self._service.last_action, self._service.last_explanation)

                if hasattr(self, "_exec_btn"):

                    self._exec_btn.setEnabled(True)

                if hasattr(self, "_cancel_btn"):

                    self._cancel_btn.setEnabled(True)

            # Append response to AI chat

            color = self.C["accent"] if response.action_type != "OPERATION_DONE" else self.C["green"]

            self._append_ai_chat("PreView AI", response.reply_text, color)

        def _append_ai_chat(self, sender: str, text: str, color: str):

            ts = datetime.now().strftime("%H:%M")

            sender_html = f"<span style='color:{color}; font-weight:700;'>{sender}</span>"

            time_html   = f"<span style='color:{self.C['text_muted']}; font-size:9px;'>{ts}</span>"

            import re

            import html as html_lib

            raw_text = text.strip()

            # Extract code blocks first to protect them from regex/linebreak replacements

            code_blocks = []

            def _save_block(m):

                lang = m.group(1) or ""

                code = m.group(2)

                code_escaped = html_lib.escape(code)

                idx = len(code_blocks)

                code_blocks.append(f"<pre style='background:#1e1b4b; border:1px solid #4338ca; border-radius:4px; padding:8px; font-family:Consolas, monospace; font-size:11px; color:#e0e7ff;'>{code_escaped}</pre>")

                return f"__CODE_BLOCK_{idx}__"

            body = re.sub(r'```([a-zA-Z0-9_-]*)\n?(.*?)```', _save_block, raw_text, flags=re.DOTALL)

            # Convert inline code `foo`

            body = re.sub(r'`([^`]+)`', r"<code style='background:#2e1065; color:#c4b5fd; padding:1px 4px; border-radius:3px; font-family:Consolas, monospace;'>\1</code>", body)

            # Convert **bold** to <b>bold</b>

            body = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', body)

            # Convert *italic* to <i>italic</i>

            body = re.sub(r'\*([^*]+?)\*', r'<i>\1</i>', body)

            # Convert linebreaks

            body = body.replace("\n", "<br>")

            # Restore code blocks

            for i, block in enumerate(code_blocks):

                body = body.replace(f"__CODE_BLOCK_{i}__", block)

            html = f"""

            <div style='margin-bottom:12px;'>

              {sender_html} &nbsp; {time_html}<br>

              <div style='color:{self.C['text_sec']}; font-size:12px; line-height:1.6;

                          margin-top:4px; padding-left:2px;'>

                {body}

              </div>

            </div>

            <hr style='border:none; border-top:1px solid {self.C['border']}; margin:8px 0;'>"""

            self._ai_chat.moveCursor(QTextCursor.End)

            self._ai_chat.insertHtml(html)

            self._ai_chat.moveCursor(QTextCursor.End)

            self._ai_chat.ensureCursorVisible()

        # ── Quick actions ─────────────────────────────────────────────────

        def _on_quick_sim_clicked(self):

            sel = getattr(self, "_selected_path", None) or self._get_active_selected_path()

            if not sel:

                self._center_tabs.setCurrentIndex(2)

                self._intent_edit.setFocus()

                return

            p = Path(sel)

            fname = p.name

            menu = QMenu(self)

            menu.setStyleSheet(f"""

                QMenu {{ background:{C['bg_panel']}; border:1px solid {C['border']};

                        color:{C['text_pri']}; padding:4px; font-size:11px; }}

                QMenu::item {{ padding:6px 14px; border-radius:4px; }}

                QMenu::item:selected {{ background:{C['accent']}; color:#fff; }}

            """)

            menu.addAction(f"⚡  Delete ({fname})", lambda: self._quick_sim_op("DELETE", fname))

            menu.addAction(f"✏️  Rename ({fname})", lambda: self._quick_sim_op("RENAME", fname))

            menu.addAction(f"📦  Move ({fname})", lambda: self._quick_sim_op("MOVE", fname))

            menu.addAction(f"📝  Modify ({fname})", lambda: self._quick_sim_op("MODIFY", fname))

            target_create = f"{fname}/new_file.py" if p.is_dir() else f"new_{fname}"

            menu.addAction(f"➕  Create ({target_create})", lambda: self._quick_sim_op("CREATE", target_create))

            sender = self.sender()

            if isinstance(sender, QWidget):

                pos = sender.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4))

                menu.exec(pos)

            else:

                menu.exec(QCursor.pos())

        def _quick_sim_op(self, op: str, target: str):

            self._center_tabs.setCurrentIndex(2)

            if op == "DELETE":

                cmd = f"delete {target}"

            elif op == "RENAME":

                cmd = f"rename {target}"

            elif op == "MOVE":

                cmd = f"move {target} to archive/"

            elif op == "MODIFY":

                cmd = f"modify {target}"

            elif op == "CREATE":

                cmd = f"create {target}"

            else:

                cmd = f"delete {target}"

            self._intent_edit.setText(cmd)

            self._run_simulation()

        def _quick_sim_delete(self):

            sel = getattr(self, "_selected_path", None) or self._get_active_selected_path()

            if sel:

                self._quick_sim_op("DELETE", Path(sel).name)

        def _quick_sim_rename(self):

            sel = getattr(self, "_selected_path", None) or self._get_active_selected_path()

            if sel:

                self._quick_sim_op("RENAME", Path(sel).name)

        def _show_graph_tab(self):

            self._center_tabs.setCurrentIndex(1)

        def _show_impact_for(self, path_str: str):

            self._selected_path = path_str

            self._on_quick_sim_clicked()

        def _show_deps_for(self, path_str: str):

            self._center_tabs.setCurrentIndex(1)

            self._update_graph_tab(highlight=path_str)

        def _get_active_selected_path(self) -> Optional[str]:

            if hasattr(self, "_file_view") and self._file_view.selectionModel():

                rows = self._file_view.selectionModel().selectedRows(0)

                if rows:

                    p = self._fs_model.filePath(rows[0])

                    if p and Path(p).exists():

                        return p

                idxs = self._file_view.selectionModel().selectedIndexes()

                if idxs:

                    p = self._fs_model.filePath(idxs[0])

                    if p and Path(p).exists():

                        return p

                idx = self._file_view.currentIndex()

                if idx.isValid():

                    p = self._fs_model.filePath(idx)

                    if p and Path(p).exists():

                        return p

            cached = getattr(self, "_selected_path", None)

            if cached and Path(cached).exists():

                return cached

            return None

        def _get_current_directory(self) -> Path:

            cur = getattr(self, "_current_dir", "") or self._path_bar.text().strip()

            if cur and Path(cur).exists() and Path(cur).is_dir():

                return Path(cur)

            if self._service.project_root and self._service.project_root.exists():

                return self._service.project_root

            return Path.cwd()

        def _detect_project_root(self, path_str: str) -> Optional[Path]:

            try:

                p = Path(path_str).resolve()

                start = p if p.is_dir() else p.parent

                start_str_lower = str(start).lower()

                is_temp = "temp" in start_str_lower or "tmp" in start_str_lower

                skip_terms = ("windows", "program files", "program files (x86)", "system volume information", "$recycle.bin")

                if not is_temp and (any(term in start_str_lower for term in skip_terms) or "appdata" in start_str_lower or "local settings" in start_str_lower):

                    return None

                for ancestor in [start] + list(start.parents):

                    if len(ancestor.parts) <= 1 or ancestor.parent == ancestor:

                        continue

                    if (ancestor / ".git").exists() or (ancestor / "requirements.txt").exists() or (ancestor / "pyproject.toml").exists() or (ancestor / "setup.py").exists():

                        return ancestor

                    if len(ancestor.parts) > 2:

                        try:

                            with os.scandir(ancestor) as it:

                                for entry in it:

                                    if entry.is_file() and entry.name.endswith(".py"):

                                        return ancestor

                        except Exception:

                            pass

            except Exception:

                pass

            return None

        def _get_consequence_analyzer(self, path_str: Optional[str] = None) -> Optional[ConsequenceAnalyzer]:

            """

            Ensure an accurate ConsequenceAnalyzer is available for path_str.

            If current graph does not cover path_str or is missing, auto-detects

            enclosing project root (walking up to find Python scripts, requirements, or git root)

            and builds the project graph.

            """

            try:

                if self._service.current_graph and self._service.project_root:

                    proj_root = self._service.project_root

                    # If project graph was indexed on a subfolder that has no scripts, auto-expand to parent project

                    if proj_root.parent != proj_root and len(proj_root.parent.parts) > 1:

                        if not any(proj_root.glob("*.py")) and any(proj_root.parent.glob("*.py")):

                            builder = GraphBuilder(proj_root.parent)

                            self._service.current_graph = builder.build()

                            self._service.project_root = proj_root.parent

                            return ConsequenceAnalyzer(self._service.current_graph)

                    if path_str:

                        p = Path(path_str).resolve()

                        try:

                            p.relative_to(proj_root.resolve())

                            return ConsequenceAnalyzer(self._service.current_graph)

                        except ValueError:

                            pass

                    else:

                        return ConsequenceAnalyzer(self._service.current_graph)

                target = path_str or str(self._get_current_directory())

                if target:

                    proj_cand = self._detect_project_root(target)

                    if proj_cand:

                        if self._service.project_root and str(self._service.project_root) == str(proj_cand) and self._service.current_graph:

                            return ConsequenceAnalyzer(self._service.current_graph)

                        # Return consequence analyzer for state graph, auto-indexing in background

                        from app.graph.builder import StateGraph

                        return ConsequenceAnalyzer(self._service.current_graph or StateGraph(proj_cand))

            except Exception as e:

                logger.warning(f"Failed to get consequence analyzer for {path_str}: {e}")

            if self._service.current_graph:

                return ConsequenceAnalyzer(self._service.current_graph)

            return None

        def _open_file(self, path_str: Optional[str] = None):

            p_str = path_str or self._get_active_selected_path()

            if not p_str or not Path(p_str).exists():

                return

            import subprocess

            try:

                os.startfile(p_str)

            except Exception:

                subprocess.Popen(["explorer", p_str])

        def _reveal_in_os_explorer(self, path_str: Optional[str] = None):

            p_str = path_str or self._get_active_selected_path() or str(self._get_current_directory())

            if not p_str or not Path(p_str).exists():

                return

            import subprocess

            p = Path(p_str).resolve()

            try:

                if p.is_file():

                    subprocess.Popen(["explorer", f"/select,{p}"])

                else:

                    subprocess.Popen(["explorer", str(p)])

            except Exception as e:

                self._log_stream(f"Could not open explorer: {e}")

        def _move_file_to_folder(self, src_path: str, dest_dir: Path):

            src = Path(src_path).resolve()

            dest_dir = dest_dir.resolve()

            if not dest_dir.exists() or not dest_dir.is_dir():

                QMessageBox.warning(self, "Invalid Destination", f"Destination folder does not exist: {dest_dir}")

                return

            if src.parent == dest_dir or src == dest_dir:

                return

            if src.is_dir():

                try:

                    dest_dir.relative_to(src)

                    QMessageBox.warning(self, "Invalid Operation", f"Cannot move folder '{src.name}' into itself or its own subfolder.")

                    return

                except ValueError:

                    pass

            dest_display = dest_dir.name if dest_dir.name else str(dest_dir)

            dest_target = dest_dir / src.name

            if dest_target.exists():

                reply = QMessageBox.question(

                    self, "File Exists",

                    f"'{dest_target.name}' already exists in '{dest_display}'.\nOverwrite it?",

                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No

                )

                if reply != QMessageBox.Yes:

                    return

                try:

                    import shutil

                    if dest_target.is_dir():

                        shutil.rmtree(str(dest_target))

                    else:

                        dest_target.unlink()

                except Exception as del_err:

                    QMessageBox.critical(self, "Overwrite Failed", f"Could not replace existing file: {del_err}")

                    return

            # Check consequences of moving

            impact: Optional[ImpactResult] = None

            try:

                analyzer = self._get_consequence_analyzer(str(src))

                if analyzer:

                    impact = analyzer.compute_impact(str(src), "MOVE", destination=str(dest_target))

            except Exception as e:

                logger.warning(f"Impact computation failed for move: {e}")

            if not impact:

                impact = ImpactResult(

                    operation="MOVE",

                    changed_path=str(src),

                    changed_object=src.name,

                    destination=str(dest_target),

                    

                    risk=RiskLevel.SAFE,

                    affected_files=[],

                    summary=f"No dependency conflicts detected for moving '{src.name}'.",

                )

            # PreView AI Consequence Dialog: Always show consequence assessment before moving

            dialog = self.ConsequenceMoveDialog(self, str(src), str(dest_target), impact, self.C, self.RISK_C)

            res = dialog.exec()

            if res != QDialog.Accepted or dialog.action_choice != "MOVE":

                if dialog.action_choice == "SIMULATE":

                    self._center_tabs.setCurrentIndex(2)

                    self._intent_edit.setText(f"move {src.name} to {dest_display}/")

                    self._run_simulation()

                return

            try:

                import shutil

                shutil.move(str(src), str(dest_target))

                self._log_stream(f"📦 Moved: '{src.name}' → '{dest_display}/{src.name}'")

                self._status.showMessage(f"Moved '{src.name}' to '{dest_display}/'")

                self._refresh()

            except Exception as e:

                QMessageBox.critical(self, "Move Failed", str(e))

        def _cut_selection(self, path_str: Optional[str] = None):

            if path_str is None and self._is_text_input_focused():

                fw = QApplication.focusWidget()

                if fw:

                    fw.cut()

                return

            if not isinstance(path_str, str) or not path_str:

                path_str = self._get_active_selected_path()

            if not path_str or not Path(path_str).exists():

                return

            self._clipboard_path = path_str

            self._clipboard_mode = "CUT"

            p = Path(path_str)

            try:

                mime = QMimeData()

                mime.setUrls([QUrl.fromLocalFile(str(p.resolve()))])

                mime.setText(str(p.resolve()))

                QApplication.clipboard().setMimeData(mime)

            except Exception:

                pass

            self._log_stream(f"✂️ Cut '{p.name}'. Ready to paste in destination folder.")

            self._status.showMessage(f"Cut '{p.name}'. Select destination and press Paste (Ctrl+V).")

            self._update_action_bar_state()

        def _copy_selection(self, path_str: Optional[str] = None):

            if path_str is None and self._is_text_input_focused():

                fw = QApplication.focusWidget()

                if fw:

                    fw.copy()

                return

            if not isinstance(path_str, str) or not path_str:

                path_str = self._get_active_selected_path()

            if not path_str or not Path(path_str).exists():

                return

            self._clipboard_path = path_str

            self._clipboard_mode = "COPY"

            p = Path(path_str)

            try:

                mime = QMimeData()

                mime.setUrls([QUrl.fromLocalFile(str(p.resolve()))])

                mime.setText(str(p.resolve()))

                QApplication.clipboard().setMimeData(mime)

            except Exception:

                pass

            self._log_stream(f"📋 Copied '{p.name}'. Ready to paste in destination folder.")

            self._status.showMessage(f"Copied '{p.name}'. Select destination and press Paste (Ctrl+V).")

            self._update_action_bar_state()

        def _paste_selection(self):

            if self._is_text_input_focused():

                fw = QApplication.focusWidget()

                if fw:

                    fw.paste()

                return

            src_str = None

            if getattr(self, "_clipboard_path", None) and Path(self._clipboard_path).exists():

                src_str = self._clipboard_path

            else:

                try:

                    c = QApplication.clipboard()

                    md = c.mimeData()

                    if md and md.hasUrls():

                        for u in md.urls():

                            lf = u.toLocalFile()

                            if lf and Path(lf).exists():

                                src_str = lf

                                break

                    if not src_str and md and md.hasText():

                        raw_text = md.text().strip().strip('"\'')

                        for line in raw_text.splitlines():

                            candidate = line.strip().strip('"\'')

                            if candidate and Path(candidate).exists():

                                src_str = candidate

                                break

                except Exception:

                    pass

            if not src_str or not Path(src_str).exists():

                QMessageBox.information(self, "Clipboard Empty", "There is no file or folder on the clipboard to paste.")

                return

            src = Path(src_str).resolve()

            sel = self._get_active_selected_path()

            if sel and Path(sel).exists() and Path(sel).is_dir():

                dest_dir = Path(sel).resolve()

            elif sel and Path(sel).exists() and Path(sel).is_file():

                dest_dir = Path(sel).parent.resolve()

            else:

                dest_dir = self._get_current_directory().resolve()

            if not dest_dir.exists() or not dest_dir.is_dir():

                QMessageBox.warning(self, "Invalid Destination", f"Destination folder does not exist: {dest_dir}")

                return

            mode = getattr(self, "_clipboard_mode", None) or "COPY"

            # --- CUT (MOVE) OPERATION ---

            if mode == "CUT":

                self._move_file_to_folder(str(src), dest_dir)

                self._clipboard_path = None

                self._clipboard_mode = None

                self._update_action_bar_state()

                return

            # --- COPY OPERATION ---

            dest_target = dest_dir / src.name

            if dest_dir == src.parent or dest_target.exists():

                stem = src.stem

                suffix = src.suffix

                counter = 1

                cand_name = f"{stem} - Copy{suffix}" if src.is_file() else f"{stem} - Copy"

                while (dest_dir / cand_name).exists():

                    counter += 1

                    cand_name = f"{stem} - Copy ({counter}){suffix}" if src.is_file() else f"{stem} - Copy ({counter})"

                dest_target = dest_dir / cand_name

            try:

                import shutil

                if src.is_dir():

                    shutil.copytree(str(src), str(dest_target))

                else:

                    shutil.copy2(str(src), str(dest_target))

                self._log_stream(f"📋 Copied: '{src.name}' → '{dest_target.name}'")

                self._status.showMessage(f"Copied '{src.name}' to '{dest_target.name}'")

                self._refresh()

            except Exception as e:

                QMessageBox.critical(self, "Copy Failed", str(e))

            self._update_action_bar_state()

        def _move_to_dialog(self, path_str: Optional[str] = None):

            if not isinstance(path_str, str) or not path_str:

                path_str = self._get_active_selected_path()

            if not path_str or not Path(path_str).exists():

                return

            src = Path(path_str).resolve()

            dest_dir_str = QFileDialog.getExistingDirectory(

                self, f"Move '{src.name}' to folder:", str(src.parent)

            )

            if not dest_dir_str:

                return

            self._move_file_to_folder(str(src), Path(dest_dir_str))

        def _copy_to_dialog(self, path_str: Optional[str] = None):

            p_str = path_str or self._get_active_selected_path()

            if not p_str or not Path(p_str).exists():

                return

            src = Path(p_str).resolve()

            dest_dir_str = QFileDialog.getExistingDirectory(

                self, f"Copy '{src.name}' to folder:", str(src.parent)

            )

            if not dest_dir_str:

                return

            dest_dir = Path(dest_dir_str).resolve()

            dest_target = dest_dir / src.name

            if dest_target.exists():

                reply = QMessageBox.question(

                    self, "File Exists",

                    f"'{dest_target.name}' already exists in destination.\nOverwrite it?",

                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No

                )

                if reply != QMessageBox.Yes:

                    return

            try:

                import shutil

                if src.is_dir():

                    shutil.copytree(str(src), str(dest_target), dirs_exist_ok=True)

                else:

                    shutil.copy2(str(src), str(dest_target))

                self._log_stream(f"📋 Copied: '{src.name}' → '{dest_dir.name}/{src.name}'")

                self._status.showMessage(f"Copied '{src.name}' to '{dest_dir.name}/'")

                self._refresh()

            except Exception as e:

                QMessageBox.critical(self, "Copy Failed", str(e))

        def _copy_as_path(self, path_str: Optional[str] = None):

            p_str = path_str or self._get_active_selected_path()

            if not p_str:

                return

            resolved = str(Path(p_str).resolve())

            QApplication.clipboard().setText(resolved)

            self._log_stream(f"🔗 Copied path: {resolved}")

            self._status.showMessage(f"Copied path to clipboard: {resolved}")

        def _new_folder(self):

            dest_dir = self._get_current_directory()

            cand = "New folder"

            count = 1

            while (dest_dir / cand).exists():

                count += 1

                cand = f"New folder ({count})"

            name, ok = QInputDialog.getText(

                self, "New Folder", "Folder name:", text=cand

            )

            if ok and name.strip():

                target = dest_dir / name.strip()

                try:

                    target.mkdir(parents=True, exist_ok=False)

                    self._log_stream(f"📁 Created folder: {target.name}")

                    self._status.showMessage(f"Created folder: {target.name}")

                    self._refresh()

                except Exception as e:

                    QMessageBox.critical(self, "Create Folder Failed", str(e))

        def _new_file(self, default_name: str = "New Document.txt"):

            dest_dir = self._get_current_directory()

            cand = default_name

            count = 1

            p_cand = Path(cand)

            while (dest_dir / cand).exists():

                count += 1

                cand = f"{p_cand.stem} ({count}){p_cand.suffix}"

            name, ok = QInputDialog.getText(

                self, "New File", "File name with extension:", text=cand

            )

            if ok and name.strip():

                target = dest_dir / name.strip()

                try:

                    target.touch(exist_ok=False)

                    self._log_stream(f"📄 Created file: {target.name}")

                    self._status.showMessage(f"Created file: {target.name}")

                    self._refresh()

                except Exception as e:

                    QMessageBox.critical(self, "Create File Failed", str(e))

        def _rename_file(self, path_str: Optional[str] = None):

            if path_str is None and self._is_text_input_focused():

                return

            if not isinstance(path_str, str) or not path_str:

                path_str = self._get_active_selected_path()

            if not path_str or not Path(path_str).exists():

                QMessageBox.warning(self, "Not Found", "No file or folder selected to rename.")

                return

            p = Path(path_str)

            # Check consequences of renaming

            impact = None

            try:

                analyzer = self._get_consequence_analyzer(str(p))

                if analyzer:

                    impact = analyzer.compute_impact(str(p), "RENAME")

            except Exception as e:

                logger.warning(f"Impact computation failed for rename: {e}")

            dialog = self.ConsequenceRenameDialog(self, str(p), impact, self.C, self.RISK_C)

            res = dialog.exec()

            if res != QDialog.Accepted or dialog.action_choice != "RENAME":

                if dialog.action_choice == "SIMULATE":

                    self._center_tabs.setCurrentIndex(2)

                    self._intent_edit.setText(f"rename {p.name} to {dialog.new_name}")

                    self._run_simulation()

                return

            new_name = dialog.new_name

            if not new_name or new_name == p.name:

                return

            new_path = p.parent / new_name

            if new_path.exists():

                QMessageBox.warning(self, "Already Exists", f"An item named '{new_name}' already exists.")

                return

            try:

                p.rename(new_path)

                self._log_stream(f"✏️ Renamed: '{p.name}' → '{new_name}'")

                self._status.showMessage(f"Renamed: '{p.name}' → '{new_name}'")

                self._selected_path = str(new_path)

                self._refresh()

            except Exception as e:

                QMessageBox.critical(self, "Rename Failed", str(e))

        def _delete_file(self, path_str: Optional[str] = None):

            if path_str is None and self._is_text_input_focused():

                return

            if not isinstance(path_str, str) or not path_str:

                path_str = self._get_active_selected_path()

            if not path_str or not Path(path_str).exists():

                QMessageBox.warning(self, "Not Found", "No file or folder selected to delete.")

                return

            p = Path(path_str)

            impact: Optional[ImpactResult] = None

            try:

                analyzer = self._get_consequence_analyzer(str(p))

                if analyzer:

                    impact = analyzer.compute_impact(str(p), "DELETE")

            except Exception as e:

                logger.warning(f"Failed to compute impact for deletion of {p}: {e}")

            dialog = self.ConsequenceDeleteDialog(self, str(p), impact, self.C, self.RISK_C)

            if dialog.exec() == QDialog.Accepted:

                if dialog.action_choice == "SIMULATE":

                    self._center_tabs.setCurrentIndex(2)

                    self._intent_edit.setText(f"delete {p.name}")

                    self._run_simulation()

                elif dialog.action_choice == "DELETE":

                    deleted_mode = None

                    try:

                        import send2trash

                        send2trash.send2trash(str(p))

                        if p.exists():

                            raise Exception("send2trash failed silently")

                        deleted_mode = "to Recycle Bin"

                    except Exception as e_trash:

                        logger.info(f"send2trash fallback to direct deletion: {e_trash}")

                        try:

                            import shutil

                            if p.is_dir():

                                shutil.rmtree(str(p))

                            else:

                                p.unlink(missing_ok=True)

                            deleted_mode = "permanently"

                        except Exception as e:

                            QMessageBox.critical(self, "Delete Failed", str(e))

                            return

                    if deleted_mode:

                        self._log_stream(f"🗑️ Deleted ({deleted_mode}): {p.name}")

                        self._status.showMessage(f"Deleted '{p.name}' ({deleted_mode})")

                        self._selected_path = None

                        self._refresh()

        def _show_properties(self, path_str: Optional[str] = None):

            p_str = path_str or self._get_active_selected_path() or str(self._get_current_directory())

            if not p_str or not Path(p_str).exists():

                return

            p = Path(p_str)

            try:

                stat = p.stat()

                size_str = _format_size(stat.st_size)

                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

                ctime = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

            except OSError:

                size_str, mtime, ctime = "0 B", "—", "—"

            kind = "Folder" if p.is_dir() else _file_kind(p.suffix.lower())

            extra_fld = ""

            if p.is_dir():

                try:

                    items = list(p.iterdir())

                    f_cnt = sum(1 for i in items if i.is_file())

                    d_cnt = sum(1 for i in items if i.is_dir())

                    extra_fld = f"\nContains: {f_cnt} file(s), {d_cnt} folder(s)"

                except Exception:

                    pass

            ai_insight = "\n\n--- PreView AI Intelligence ---"

            if self._service.current_graph:

                analyzer = self._get_consequence_analyzer(str(p))

                if analyzer:

                    impact = analyzer.compute_impact(str(p), "DELETE")

                    aff_cnt = len(impact.affected_files)

                    ai_insight += f"\nImpact Risk if Removed: {impact.risk.value}"

                    ai_insight += f"\nDependent Files in Project: {aff_cnt}"

                    if aff_cnt > 0:

                        dep_names = ", ".join(f.name for f in impact.affected_files[:3])

                        ai_insight += f" ({dep_names})"

                else:

                    ai_insight += "\nProject: Not indexed in active graph."

            else:

                ai_insight += "\nProject: Folder not yet indexed (click '⚡ Index as Project' to map)."

            msg = (

                f"Name: {p.name}\n"

                f"Type: {kind}\n"

                f"Location: {str(p.parent)}\n"

                f"Size: {size_str}{extra_fld}\n\n"

                f"Created: {ctime}\n"

                f"Modified: {mtime}"

                f"{ai_insight}"

            )

            QMessageBox.information(self, f"Properties — {p.name}", msg)

        def _on_enter_pressed(self):

            if self._is_text_input_focused():

                return

            idx = self._file_view.currentIndex()

            if idx.isValid():

                self._on_file_double_clicked(idx)

        def _update_action_bar_state(self, *args, **kwargs):

            sel = self._get_active_selected_path()

            has_sel = bool(sel and Path(sel).exists())

            has_clip = False

            if getattr(self, "_clipboard_path", None) and Path(self._clipboard_path).exists():

                has_clip = True

            else:

                try:

                    c = QApplication.clipboard()

                    md = c.mimeData()

                    if md and md.hasUrls():

                        urls = md.urls()

                        if urls and any(Path(u.toLocalFile()).exists() for u in urls):

                            has_clip = True

                except Exception:

                    pass

            if hasattr(self, "_cmd_bar") and hasattr(self._cmd_bar, "update_action_state"):

                self._cmd_bar.update_action_state(has_sel, has_clip)

            for btn_name in ("_btn_cut", "_btn_copy", "_btn_rename", "_btn_delete",

                             "_btn_moveto", "_btn_copyto", "_btn_copypath", "_btn_sim_act",

                             "_act_cut", "_act_copy", "_act_rename", "_act_delete",

                             "_act_moveto", "_act_copyto", "_act_copypath", "_act_sim_act"):

                if hasattr(self, btn_name):

                    getattr(self, btn_name).setEnabled(has_sel)

            for paste_name in ("_btn_paste", "_act_paste"):

                if hasattr(self, paste_name):

                    getattr(self, paste_name).setEnabled(has_clip)

            if hasattr(self, "_act_os_exp"):

                self._act_os_exp.setEnabled(has_sel or bool(self._current_dir))

        def _simulate_selected_item(self):

            sel = self._get_active_selected_path()

            if sel:

                self._selected_path = sel

            self._on_quick_sim_clicked()

        # ── Graph tab ─────────────────────────────────────────────────────

        def _update_graph_tab(self, highlight: Optional[str] = None):

            if not self._service.current_graph:

                self._graph_text.setHtml(f"""

                    <div style='padding:24px; font-family:Segoe UI,sans-serif; color:{self.C['text_muted']}; text-align:center;'>

                        <div style='font-size:32px; margin-bottom:8px;'>🧭</div>

                        <div style='font-size:15px; font-weight:bold; color:{self.C['text_sec']};'>No Project Graph Available</div>

                        <div style='font-size:12px; margin-top:6px;'>Open a project folder and click <b>⚡ Index as Project</b> to map component relationships.</div>

                    </div>

                """)

                return

            from collections import defaultdict

            g = self._service.current_graph

            proj_name = self._service.project_root.name

            # Group edges by target and source

            incoming_edges = defaultdict(list)

            outgoing_edges = defaultdict(list)

            for edge in g.edges:

                incoming_edges[edge.target_id].append(edge)

                outgoing_edges[edge.source_id].append(edge)

            bg_card = self.C["bg_card"]

            border = self.C["border"]

            text_pri = self.C["text_pri"]

            text_sec = self.C["text_sec"]

            text_muted = self.C["text_muted"]

            accent = self.C["accent"]

            # Compute graph-wide impact states relative to highlight

            selected_ids = set()

            direct_ids = set()

            indirect_ids = set()

            if highlight:

                hl_p = Path(highlight)

                hl_name = hl_p.name

                hl_str = str(hl_p)

                for nid, n in g.nodes.items():

                    if nid == hl_str or n.name == hl_name or n.path == hl_str:

                        selected_ids.add(nid)

                        selected_ids.add(n.path)

                        selected_ids.add(n.name)

                # Direct dependents

                for sid in list(selected_ids):

                    for edge in incoming_edges.get(sid, []):

                        direct_ids.add(edge.source_id)

                        sn = g.get_node(edge.source_id)

                        if sn:

                            direct_ids.add(sn.name)

                            direct_ids.add(sn.path)

                # Indirect dependents

                for did in list(direct_ids):

                    for edge in incoming_edges.get(did, []):

                        if edge.source_id not in direct_ids and edge.source_id not in selected_ids:

                            indirect_ids.add(edge.source_id)

                            sn = g.get_node(edge.source_id)

                            if sn:

                                indirect_ids.add(sn.name)

                                indirect_ids.add(sn.path)

            def edge_badge(op):

                badge_colors = {

                    "LOADS": "#7c3aed",

                    "READS": "#0284c7",

                    "IMPORTS": "#16a34a",

                    "REFERENCES": "#d97706",

                    "DECLARES": "#2563eb",

                }

                c = badge_colors.get(op, "#64748b")

                return f"<span style='background:{c}; color:#ffffff; font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px;'>{op}</span>"

            html = f"""

            <div style='font-family:Segoe UI,sans-serif; padding:12px; color:{text_pri};'>

              <!-- Architecture Summary Card -->

              <table width='100%' cellpadding='14' cellspacing='0' style='background:{bg_card}; border:1px solid {border}; border-radius:8px;'>

                <tr>

                  <td>

                    <div style='font-size:15px; font-weight:700; color:{text_pri};'>🏗️ Project Architecture: {proj_name}</div>

                    <div style='font-size:11px; color:{text_sec}; margin-top:6px;'>

                      <b>{g.node_count}</b> Files &nbsp; • &nbsp; <b>{g.edge_count}</b> Verified Connections &nbsp; • &nbsp; Local Deterministic AST & Pattern Engine

                    </div>

                    <div style='margin-top:10px; font-size:10px; color:{text_muted};'>

                      <b>Legend:</b> &nbsp;

                      <span style='background:#7c3aed; color:#fff; padding:2px 6px; border-radius:3px;'>📌 Selected</span> &nbsp;

                      <span style='background:#059669; color:#fff; padding:2px 6px; border-radius:3px;'>⚡ Direct Dependent</span> &nbsp;

                      <span style='background:#d97706; color:#fff; padding:2px 6px; border-radius:3px;'>⚠️ Indirect Dependent</span> &nbsp;

                      <span style='background:#475569; color:#fff; padding:2px 6px; border-radius:3px;'>⚪ Unaffected</span>

                    </div>

                  </td>

                </tr>

              </table>

              <div style='height:14px; font-size:14px; line-height:14px;'>&nbsp;</div>

              <div style='font-size:11px; font-weight:700; color:{text_muted}; letter-spacing:0.8px; margin-bottom:8px; text-transform:uppercase;'>

                WORKFLOW & DATA PIPELINE — Component Dependencies (Ranked by Impact Risk) — Click any component to inspect:

              </div>

            """

            target_ids = sorted(incoming_edges.keys(), key=lambda t: len(incoming_edges[t]), reverse=True)

            for i, tid in enumerate(target_ids):

                tgt_node = g.get_node(tid) or g.find_node_by_name(tid)

                raw_name = Path(tid).name if not tid.startswith("package:") else tid[8:]

                tgt_name = tgt_node.name if tgt_node else raw_name

                tgt_path = tgt_node.path if tgt_node else tid

                dep_count = len(incoming_edges[tid])

                is_selected = highlight and (tid in selected_ids or tgt_name in selected_ids or tgt_path in selected_ids)

                is_direct   = highlight and (tid in direct_ids or tgt_name in direct_ids or tgt_path in direct_ids)

                is_indirect = highlight and (tid in indirect_ids or tgt_name in indirect_ids or tgt_path in indirect_ids)

                if is_selected:

                    status_badge = "<span style='background:#7c3aed; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px; border-radius:3px; margin-left:8px;'>📌 SELECTED FILE</span>"

                    hl_border = "border:2px solid #a855f7; box-shadow:0 0 10px rgba(168,85,247,0.3);"

                elif is_direct:

                    status_badge = "<span style='background:#059669; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px; border-radius:3px; margin-left:8px;'>⚡ DIRECT DEPENDENCY</span>"

                    hl_border = "border:2px solid #10b981;"

                elif is_indirect:

                    status_badge = "<span style='background:#d97706; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px; border-radius:3px; margin-left:8px;'>⚠️ INDIRECT DEPENDENCY</span>"

                    hl_border = "border:2px solid #f59e0b;"

                else:

                    if dep_count >= 2:

                        status_badge = "<span style='background:#ef4444; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px; border-radius:3px; margin-left:8px;'>CRITICAL HUB</span>"

                    else:

                        status_badge = "<span style='background:#475569; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px; border-radius:3px; margin-left:8px;'>⚪ UNAFFECTED FILE</span>"

                    hl_border = f"border:1px solid {border};"

                if tid.endswith((".pkl", ".pt", ".h5")):

                    icon = "🧠"

                elif tid.endswith((".csv", ".tsv")):

                    icon = "📊"

                elif tid.endswith(".py"):

                    icon = "🐍"

                elif not tgt_node:

                    icon = "📦"

                else:

                    icon = "📄"

                html += f"""

                <table width='100%' cellpadding='14' cellspacing='0' style='background:{bg_card}; {hl_border} border-radius:8px;'>

                  <tr>

                    <td>

                      <div style='font-size:13px; font-weight:700; color:{text_pri}; margin-bottom:4px;'>

                        <a href='select:{tgt_path}' style='color:{text_pri}; text-decoration:none;'>{icon} <b>{tgt_name}</b></a> {status_badge}

                      </div>

                      <div style='font-size:10px; color:{text_muted}; margin-bottom:8px;'>

                        Location: <a href='select:{tgt_path}' style='color:{text_muted};'>{tgt_path}</a>

                      </div>

                      <div style='font-size:11px; font-weight:600; color:{text_sec}; margin-bottom:8px;'>

                        Required by {dep_count} component(s):

                      </div>

                """

                for edge in incoming_edges[tid]:

                    src_node = g.get_node(edge.source_id) or g.find_node_by_name(edge.source_id)

                    src_name = src_node.name if src_node else Path(edge.source_id).name

                    src_path = src_node.path if src_node else edge.source_id

                    badge = edge_badge(edge.edge_type.value)

                    loc_str = ""

                    if edge.evidence:

                        ev = edge.evidence[0]

                        loc_str = f"at line {ev.line_number}" if ev.line_number else ""

                    if edge.edge_type.value == "LOADS":

                        human_desc = f"<a href='select:{src_path}' style='color:{accent}; font-weight:bold; text-decoration:none;'>{src_name}</a> loads this model directly into memory ({loc_str})."

                    elif edge.edge_type.value == "READS":

                        human_desc = f"<a href='select:{src_path}' style='color:{accent}; font-weight:bold; text-decoration:none;'>{src_name}</a> reads this dataset ({loc_str})."

                    elif edge.edge_type.value == "IMPORTS":

                        human_desc = f"<a href='select:{src_path}' style='color:{accent}; font-weight:bold; text-decoration:none;'>{src_name}</a> imports functions/classes ({loc_str})."

                    elif edge.edge_type.value == "DECLARES":

                        human_desc = f"<a href='select:{src_path}' style='color:{accent}; font-weight:bold; text-decoration:none;'>{src_name}</a> declares this package dependency."

                    else:

                        human_desc = f"<a href='select:{src_path}' style='color:{accent}; font-weight:bold; text-decoration:none;'>{src_name}</a> references this component ({loc_str})."

                    html += f"""

                      <table width='100%' cellpadding='6' cellspacing='0' style='background:{self.C['bg_deep']}; border:1px solid {border}; border-radius:6px; margin-top:5px;'>

                        <tr>

                          <td style='font-size:11px;'>

                            {badge} &nbsp; <span style='color:{text_pri};'>{human_desc}</span>

                          </td>

                        </tr>

                      </table>

                      <div style='height:4px; font-size:4px; line-height:4px;'>&nbsp;</div>

                    """

                html += f"""

                    </td>

                  </tr>

                </table>

                <div style='height:16px; font-size:16px; line-height:16px;'>&nbsp;</div>

                <hr style='border:none; border-top:1px dashed {border}; margin:4px 0 16px 0;'>

                <div style='height:8px; font-size:8px; line-height:8px;'>&nbsp;</div>

                """

            all_depended_names = {g.get_node(t).name for t in target_ids if g.get_node(t)}

            leaf_files = [n for n in g.nodes.values() if n.name not in all_depended_names and not incoming_edges.get(n.node_id)]

            if leaf_files:

                leaf_pills = "".join(

                    f"<a href='select:{n.path}' style='display:inline-block; background:{self.C['bg_deep']}; border:1px solid {border}; border-radius:4px; padding:4px 10px; margin:4px 8px 4px 0; font-size:11px; color:{text_sec}; text-decoration:none;'>📄 {n.name}</a>"

                    for n in leaf_files

                )

                html += f"""

                <table width='100%' cellpadding='14' cellspacing='0' style='background:{bg_card}; border:1px solid {border}; border-radius:8px;'>

                  <tr>

                    <td>

                      <div style='font-size:12px; font-weight:700; color:{self.C['green']}; margin-bottom:8px;'>

                        🛡️ Leaf / Independent Components (Safe to modify without breaking project dependents)

                      </div>

                      <div style='line-height:2.2;'>

                        {leaf_pills}

                      </div>

                    </td>

                  </tr>

                </table>

                """

            html += "</div>"

            self._graph_text.setHtml(html)

        def _on_graph_anchor_clicked(self, url):

            """Handle clicking on graph node anchors to select and inspect file."""

            u_str = url.toString() if hasattr(url, "toString") else str(url)

            if u_str.startswith("select:"):

                target_path = u_str[7:]

            elif u_str.startswith("file:"):

                target_path = u_str[5:]

            else:

                target_path = u_str

            if target_path and Path(target_path).exists():

                p = Path(target_path)

                if p.is_file():

                    self._navigate_to(str(p.parent))

                    self._selected_path = str(p)

                    self._update_preview(str(p))

                    self._highlight_file_in_view(str(p))

                    self._update_graph_tab(highlight=str(p))

                    self._status.showMessage(f"Selected from Graph: {p.name}")

                elif p.is_dir():

                    self._navigate_to(str(p))

        # ─── Search & Scope ──────────────────────────────────────────────────

        def _set_search_scope(self, scope: str):

            self._search_scope = scope

            scope_labels = {

                "PROJECT": "Scope: Project ▾",

                "FOLDER": "Scope: Folder ▾",

                "LOCATIONS": "Scope: Locations ▾"

            }

            if hasattr(self, "_search_scope_btn"):

                self._search_scope_btn.setText(scope_labels.get(scope, f"Scope: {scope.title()} ▾"))

            self._status.showMessage(f"Search scope set to: {scope.title()}")

            if hasattr(self, "_search_box") and self._search_box.text().strip():

                self._on_search(self._search_box.text())

        def _add_search_location(self):

            folder = QFileDialog.getExistingDirectory(self, "Select Approved Location to Index & Search")

            if not folder:

                return

            p = Path(folder)

            if not hasattr(self, "_user_approved_locations"):

                self._user_approved_locations = []

            if p not in self._user_approved_locations:

                self._user_approved_locations.append(p)

                self._log_stream(f"Added approved search location: {p}")

                self._status.showMessage(f"Added search location: {p.name}")

                self._set_search_scope("LOCATIONS")

        def _highlight_file_in_view(self, file_path: str):
            """Select and scroll to the specified file or folder in the Explorer view."""
            if hasattr(self, "_fs_model") and hasattr(self, "_file_view"):
                idx = self._fs_model.index(str(file_path))
                if idx.isValid():
                    self._file_view.setCurrentIndex(idx)
                    self._file_view.scrollTo(idx)

        def _on_search(self, text: str):
            text = text.strip()
            if not text:
                self._fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
                self._fs_model.setNameFilters([])
                self._fs_model.setNameFilterDisables(False)
                self._status.showMessage(f"Browsing: {self._current_dir or ''}")
                return

            scope = getattr(self, "_search_scope", "PROJECT")

            # Enable filtering for both files and folders matching the search query
            self._fs_model.setFilter(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)
            self._fs_model.setNameFilters([f"*{text}*"])
            self._fs_model.setNameFilterDisables(False)

            # Count immediate matches in current directory (files and folders)
            cur = Path(self._current_dir) if hasattr(self, "_current_dir") and self._current_dir else Path.cwd()
            file_matches = 0
            folder_matches = 0
            try:
                for entry in cur.iterdir():
                    if text.lower() in entry.name.lower():
                        if entry.is_dir():
                            folder_matches += 1
                        else:
                            file_matches += 1
            except Exception:
                pass

            total_cur = file_matches + folder_matches

            if scope == "FOLDER":
                if total_cur == 0:
                    self._status.showMessage(f"No files or folders match '{text}' in current folder.")
                else:
                    self._status.showMessage(f"Filtered by '{text}' in current folder — {file_matches} file(s), {folder_matches} folder(s) found")
            else:
                # In Project scope, also count project-wide matches across files and folders
                proj_matches = 0
                proj_root = getattr(self._service, "project_root", None)
                if proj_root and Path(proj_root).exists():
                    try:
                        for p in Path(proj_root).rglob("*"):
                            if any(part.startswith(".") or part in ("__pycache__", "node_modules", ".venv") for part in p.parts):
                                continue
                            if text.lower() in p.name.lower():
                                proj_matches += 1
                    except Exception:
                        pass

                msg = f"Found {total_cur} match(es) in folder"
                if proj_matches > 0:
                    msg += f", {proj_matches} across project"
                msg += f" for '{text}'. Press Enter to jump to file or folder."
                self._status.showMessage(msg)

        def _on_search_enter(self):
            text = self._search_box.text().strip()
            if not text:
                return

            best_path = None
            cur = Path(self._current_dir) if hasattr(self, "_current_dir") and self._current_dir else Path.cwd()

            # 1. Search current directory first (check exact name match first, then substring)
            try:
                for entry in cur.iterdir():
                    if text.lower() == entry.name.lower():
                        best_path = entry
                        break
                    elif text.lower() in entry.name.lower() and not best_path:
                        best_path = entry
            except Exception:
                pass

            # 2. If not found in current folder, search across the project root (files and folders)
            if not best_path:
                proj_root = getattr(self._service, "project_root", None)
                search_roots = [Path(proj_root)] if (proj_root and Path(proj_root).exists()) else [cur]
                for sroot in search_roots:
                    try:
                        for p in sroot.rglob("*"):
                            if any(part.startswith(".") or part in ("__pycache__", "node_modules", ".venv") for part in p.parts):
                                continue
                            if text.lower() == p.name.lower():
                                best_path = p
                                break
                            elif text.lower() in p.name.lower() and not best_path:
                                best_path = p
                        if best_path:
                            break
                    except Exception:
                        pass

            # 3. Fallback to dependency graph nodes
            if not best_path:
                g = getattr(self._service, "dependency_graph", None)
                if g and hasattr(g, "nodes"):
                    for nid, node in g.nodes.items():
                        if text.lower() == node.name.lower():
                            best_path = Path(node.path)
                            break
                        elif text.lower() in node.name.lower() and not best_path:
                            best_path = Path(node.path)

            if best_path and Path(best_path).exists():
                p = Path(best_path)
                if p.is_dir():
                    self._navigate_to(str(p))
                    self._selected_path = str(p)
                    self._update_preview(str(p))
                    self._highlight_file_in_view(str(p))
                    self._status.showMessage(f"Opened folder: {p.name}")
                else:
                    self._navigate_to(str(p.parent))
                    self._selected_path = str(p)
                    self._update_preview(str(p))
                    self._highlight_file_in_view(str(p))
                    self._status.showMessage(f"Jumped to file: {p.name}")
            else:
                self._status.showMessage(f"No file or folder found matching '{text}'.")

        # ─── Demo Mode & Quick Actions ──────────────────────────────────────

        def _launch_demo_mode(self):

            """Load the official ML demo project and display guided prompt."""

            demo_dir = _PROJECT_ROOT / "examples" / "demo_ml_project"

            if not demo_dir.exists():

                QMessageBox.warning(self, "Demo Not Found", f"Demo project not found at {demo_dir}")

                return

            self._navigate_to(str(demo_dir))

            self._start_scan(str(demo_dir))

            dataset_file = demo_dir / "dataset.csv"

            if dataset_file.exists():

                self._selected_path = str(dataset_file)

                self._update_preview(str(dataset_file))

                self._highlight_file_in_view(str(dataset_file))

            self._ai_btn.setChecked(True)

            if not self._ai_open:

                self._toggle_ai_panel()

            demo_msg = (

                "🎬 <b>60-Second Demo Mode Active</b><br><br>"

                "Target: <code>examples/demo_ml_project</code><br>"

                "Selected: <code>dataset.csv</code><br><br>"

                "<b>Suggested Guided Questions:</b><br>"

                "1. <i>What is this project?</i><br>"

                "2. <i>What uses dataset.csv?</i><br>"

                "3. <i>What happens if I delete dataset.csv?</i><br>"

                "4. <i>Move dataset.csv into data/</i><br><br>"

                "<i>PreView AI uses deterministic AST graph analysis, local ONNX impact prediction, and verified file execution.</i>"

            )

            self._append_ai_chat("System", demo_msg, self.C["accent"])

            self._status.showMessage("Demo project loaded. Select dataset.csv to explore consequence simulation.")

        def _on_quick_ask_ai(self):

            if not self._selected_path:

                QMessageBox.information(self, "Select a File", "Please select a file to ask PreView AI about.")

                return

            self._ask_ai_about(self._selected_path)

        def _on_quick_modify(self):

            if not self._selected_path:

                QMessageBox.information(self, "Select a File", "Please select a file to modify.")

                return

            fname = Path(self._selected_path).name

            self._ask_ai_about(self._selected_path)

            if hasattr(self, "_ai_input"):

                self._ai_input.setText(f"Modify {fname} to ")

                self._ai_input.setFocus()

        # ─── Operation History ──────────────────────────────────────────────

        def _record_operation_history(self, op: str, source: str, destination: str, status: str, verification_msg: str, diff: str = ""):

            ts = datetime.now().strftime("%H:%M")

            entry = {

                "timestamp": ts,

                "operation": op,

                "source": source,

                "destination": destination,

                "status": status,

                "verification": verification_msg,

                "diff": diff

            }

            if not hasattr(self, "_operation_history"):

                self._operation_history = []

            self._operation_history.append(entry)

            if hasattr(self, "_op_history_tree"):

                src_name = Path(source).name if source else "-"

                parent_item = QTreeWidgetItem(self._op_history_tree, [

                    ts, op, src_name, status, verification_msg or "Verified"

                ])

                status_color = "#10b981" if ("✓" in status or status.lower() == "verified") else ("#ef4444" if ("fail" in status.lower() or "✗" in status) else "#f59e0b")

                parent_item.setForeground(3, QColor(status_color))

                QTreeWidgetItem(parent_item, ["", "Source Path", source, "", ""])

                if destination:

                    QTreeWidgetItem(parent_item, ["", "Destination", destination, "", ""])

                if verification_msg:

                    QTreeWidgetItem(parent_item, ["", "Verification", verification_msg, "", ""])

                if diff:

                    diff_first = diff.strip().splitlines()[0] if diff.strip().splitlines() else "Diff recorded"

                    QTreeWidgetItem(parent_item, ["", "Changes", diff_first, "", ""])

                parent_item.setExpanded(True)

                self._op_history_tree.scrollToBottom()

        def _clear_operation_history(self):

            if hasattr(self, "_operation_history"):

                self._operation_history.clear()

            if hasattr(self, "_op_history_tree"):

                self._op_history_tree.clear()

        # ── Event stream ───────────────────────────────────────────────────

        def _log_stream(self, msg: str):

            ts = datetime.now().strftime("%H:%M:%S")

            color = self.C["text_sec"]

            if any(k in msg for k in ("ERROR", "BLOCKED", "failed")):

                color = self.C["red"]

            elif any(k in msg for k in ("✓", "Indexed", "done", "started")):

                color = self.C["green"]

            elif any(k in msg for k in ("⚠", "AFFECTED", "WARNING")):

                color = self.C["yellow"]

            elif "[USER MADE]" in msg:

                color = self.C["cyan"]

            elif "Simulation" in msg or "⚡" in msg:

                color = self.C["accent"]

            html = (

                f"<span style='color:{self.C['text_muted']};'>[{ts}]</span> "

                f"<span style='color:{color};'>{msg}</span><br>"

            )

            # Cap event stream buffer to keep performance ultra-fast

            if self._event_stream.document().blockCount() > 150:

                cursor = self._event_stream.textCursor()

                cursor.movePosition(QTextCursor.Start)

                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 40)

                cursor.removeSelectedText()

            self._event_stream.moveCursor(QTextCursor.End)

            self._event_stream.insertHtml(html)

            self._event_stream.moveCursor(QTextCursor.End)

            # Mirror to service history

            self._service.event_history.append((ts, msg, None))

        def _clear_stream(self):

            self._event_stream.clear()

        def closeEvent(self, event):

            if hasattr(self, "_ai_floating_window") and self._ai_floating_window:

                self._ai_floating_window.close()

            for worker_attr in ("_scan_worker", "_impact_worker", "_sim_worker"):

                worker = getattr(self, worker_attr, None)

                if worker and worker.isRunning():

                    worker.wait(1000)

            self._service.stop_watcher()

            super().closeEvent(event)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _small_bold_font():

        f = QFont(); f.setPointSize(8); f.setBold(True); return f

    def _file_icon(ext: str) -> str:

        return {

            ".py": "🐍", ".json": "⚙", ".yaml": "⚙", ".yml": "⚙",

            ".csv": "📊", ".txt": "📄", ".md": "📝",

            ".pkl": "📦", ".pt": "🤖", ".h5": "🤖", ".onnx": "🤖",

            ".bat": "⚡", ".sh": "⚡", ".ps1": "⚡",

            ".png": "🖼", ".jpg": "🖼", ".jpeg": "🖼",

            ".zip": "🗜", ".tar": "🗜", ".gz": "🗜",

        }.get(ext, "📄")

    def _file_kind(ext: str) -> str:

        return {

            ".py": "Python Script", ".json": "JSON Config", ".yaml": "YAML Config",

            ".yml": "YAML Config", ".csv": "CSV Data", ".txt": "Text File",

            ".md": "Markdown", ".pkl": "Pickle Model", ".pt": "PyTorch Model",

            ".h5": "HDF5 Model", ".onnx": "ONNX Model",

            ".bat": "Batch Script", ".sh": "Shell Script", ".ps1": "PowerShell",

            ".png": "PNG Image", ".jpg": "JPEG Image",

        }.get(ext, f"{ext.upper().lstrip('.')} File" if ext else "Folder")

    def _format_size(n: int) -> str:

        for unit in ("B", "KB", "MB", "GB"):

            if n < 1024:

                return f"{n:.1f} {unit}"

            n /= 1024

        return f"{n:.1f} TB"

    window = PreViewWindow()

    window.show()

    if start_loop:

        sys.exit(app.exec())

    return window

# ══════════════════════════════════════════════════════════════════════════════

# CLI mode (unchanged from previous session)

# ══════════════════════════════════════════════════════════════════════════════

def run_cli_mode(service: PreViewAIService, project_path=None, action_intent=None):

    print("=" * 60)

    print(" PreView AI — Impact Awareness System (CLI)")

    print("=" * 60)

    target = Path(project_path) if project_path else Path.cwd()

    print(f"Project: {target.resolve()}")

    service.load_project(str(target))

    intent = action_intent or input("\nProposed action> ").strip()

    if not intent:

        return

    print("\nSimulating…")

    ok, msg, data = service.simulate_intent(intent)

    if not ok:

        print(f"\n⛔ BLOCKED: {msg}")

        return

    impact: ImpactResult = data["impact"]

    action = data["action"]

    explanation = data["explanation"]

    print(f"\nRisk: {impact.risk.value}")

    print(f"Operation: {action.operation} → {action.target}")

    print(f"\n{impact.summary}")

    if impact.affected_files:

        print("\nAFFECTED FILES:")

        for i, f in enumerate(impact.affected_files, 1):

            print(f"  {i}. {f.name}  [{f.confidence.value}]")

            print(f"     {f.description}")

            print(f"     Evidence: {f.evidence_summary}")

    else:

        print("\n✓ No confirmed dependent files detected.")

    if impact.downstream_files:

        print("\nDOWNSTREAM:")

        for f in impact.downstream_files:

            print(f"  ↳ {f.name}")

    print(f"\n{explanation}")

    print("\n" + "-" * 60)

    confirm = input("Approve & execute? (y/N): ").strip().lower()

    if confirm == "y":

        ok, msg, d = service.execute_and_verify()

        print(f"Result: {msg}")

        ver = d.get("verification")

        if ver:

            print(f"Verification: {ver.status}")

    else:

        print("Cancelled. No files modified.")

# ══════════════════════════════════════════════════════════════════════════════

# Entry point

# ══════════════════════════════════════════════════════════════════════════════

def main():

    parser = argparse.ArgumentParser(description="PreView AI")

    parser.add_argument("--project", type=str)

    parser.add_argument("--action",  type=str)

    parser.add_argument("--cli",     action="store_true")

    parser.add_argument("--diagnostics", action="store_true", help="Print Snapdragon AI & hardware diagnostic report")

    parser.add_argument("--snapdragon-check", action="store_true", help="Alias for --diagnostics")

    args = parser.parse_args()

    if args.diagnostics or args.snapdragon_check:

        from app.ai.model_manager import ModelManager

        mm = ModelManager()

        print(mm.format_diagnostics())

        return

    service = PreViewAIService(project_root=args.project)

    if args.cli or args.action:

        run_cli_mode(service, project_path=args.project, action_intent=args.action)

    else:

        try:
            run_gui_mode(service, project_path=args.project)
        except Exception as e:
            logger.error(f"GUI initialization failed: {e}", exc_info=True)
            if os.environ.get("PREVIEW_AI_FALLBACK_CLI", "0") == "1":
                logger.warning("Falling back to CLI due to PREVIEW_AI_FALLBACK_CLI setting.")
                run_cli_mode(service, project_path=args.project, action_intent=args.action)
            else:
                show_fatal_gui_error(
                    "PreView AI — Startup Error",
                    f"PreView AI could not start due to an initialization error:\n\n{e}\n\nPlease check your system dependencies or view the diagnostic logs.",
                    APPLICATION_LOG_FILE
                )
                raise

if __name__ == "__main__":

    main()
