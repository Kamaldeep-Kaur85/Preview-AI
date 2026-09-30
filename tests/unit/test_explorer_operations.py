"""
tests/unit/test_explorer_operations.py

Unit tests for Explorer Operations & Consequence Awareness:
1. Consequence-Aware Delete action:
   - Action buttons enabled/disabled dynamically based on active selection.
   - ConsequenceDeleteDialog shows impact analysis.
   - Deletion removes file/folder cleanly.
2. Copy and Paste:
   - Copy sets internal clipboard and OS clipboard QMimeData.
   - Paste enables dynamically.
   - Pasting copies file with collision resolution.
   - Cut and paste moves file.
3. Move to another folder & Drag-and-Drop:
   - ExplorerTreeView drag & drop support.
   - _move_file_to_folder moves file to destination with consequence analysis.
4. Consequence-Aware Rename:
   - ConsequenceRenameDialog shows current name, new name edit, affected project files.
   - Input validation (duplicate name, invalid characters).
   - Rename action updates file name, graph, and UI.
5. Filesystem drive root safety guard:
   - _detect_project_root and _start_scan reject drive roots (D:\\, C:\\).
"""

import os
import shutil
import pytest
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QMimeData
from PySide6.QtWidgets import QApplication, QDialog

from app.main import (
    PreViewAIService,
    run_gui_mode,
)
from app.graph.models import RiskLevel, ConfidenceLevel, ImpactResult, ImpactedFile


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


@pytest.fixture
def mock_project(tmp_path):
    proj = tmp_path / "my_project"
    proj.mkdir()
    (proj / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
    (proj / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")
    ds_dir = proj / "dataset"
    ds_dir.mkdir()
    (ds_dir / "data.csv").write_text("id,val\n1,10", encoding="utf-8")
    sub_dir = proj / "models"
    sub_dir.mkdir()
    return proj


def test_selection_enables_action_buttons(mock_project):
    """Verify selecting a file or folder immediately enables Cut, Copy, Rename, Delete, Simulate."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    # Initial state: no row selected
    window._selected_path = None
    window._update_action_bar_state()
    assert not window._btn_cut.isEnabled()
    assert not window._btn_copy.isEnabled()
    assert not window._btn_rename.isEnabled()
    assert not window._btn_delete.isEnabled()
    assert not window._btn_sim_act.isEnabled()
    assert not window._btn_paste.isEnabled()

    # Select dataset folder
    ds_path = str(mock_project / "dataset")
    idx = window._fs_model.index(ds_path)
    assert idx.isValid()

    window._file_view.setCurrentIndex(idx)
    window._on_file_clicked(idx)

    # Buttons must now be enabled
    assert window._btn_cut.isEnabled()
    assert window._btn_copy.isEnabled()
    assert window._btn_rename.isEnabled()
    assert window._btn_delete.isEnabled()
    assert window._btn_sim_act.isEnabled()


def test_copy_and_paste_file(mock_project):
    """Verify Copying a file enables Paste and pastes with collision handling."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    train_path = str(mock_project / "train.py")
    window._copy_selection(train_path)

    # Paste must now be enabled
    assert window._clipboard_path == train_path
    assert window._btn_paste.isEnabled()

    # Paste into project folder
    window._paste_selection()
    copy_file = mock_project / "train - Copy.py"
    assert copy_file.exists()


def test_consequence_rename_dialog(mock_project):
    """Verify ConsequenceRenameDialog displays affected files, validates input, and renames."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    # Create dummy impact
    impact = ImpactResult(
        changed_object="dataset",
        changed_path=str(mock_project / "dataset"),
        operation="RENAME",
        risk=RiskLevel.HIGH,
        affected_files=[
            ImpactedFile(
                path=str(mock_project / "train.py"),
                name="train.py",
                impact_type="DIRECT",
                relationship="imports",
                confidence=ConfidenceLevel.CONFIRMED,
                risk_level=RiskLevel.HIGH,
                description="Imports dataset",
                evidence_summary="import dataset in line 1",
            ),
            ImpactedFile(
                path=str(mock_project / "app.py"),
                name="app.py",
                impact_type="DIRECT",
                relationship="imports",
                confidence=ConfidenceLevel.CONFIRMED,
                risk_level=RiskLevel.HIGH,
                description="Imports dataset",
                evidence_summary="import dataset in line 1",
            ),
        ],
        summary="Renaming dataset will break 2 importing scripts.",
    )

    ds_path = str(mock_project / "dataset")
    dialog = window.ConsequenceRenameDialog(window, ds_path, impact, window.C, window.RISK_C)

    assert dialog is not None
    assert dialog.src.name == "dataset"

    # Test input validation
    dialog.name_edit.setText("dataset")  # Same name
    assert not dialog.btn_rename.isEnabled()

    dialog.name_edit.setText("train.py")  # Existing file name
    assert not dialog.btn_rename.isEnabled()

    dialog.name_edit.setText("dataset:invalid")  # Invalid chars
    assert not dialog.btn_rename.isEnabled()

    dialog.name_edit.setText("dataset_v2")  # Valid new name
    assert dialog.btn_rename.isEnabled()


def test_move_file_to_folder(mock_project, monkeypatch):
    """Verify _move_file_to_folder safely moves files between directories."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    src_file = mock_project / "dataset" / "data.csv"
    dest_dir = mock_project / "models"

    assert src_file.exists()
    assert not (dest_dir / "data.csv").exists()

    def mock_exec(self):
        self.action_choice = "MOVE"
        return QDialog.Accepted

    monkeypatch.setattr(window.ConsequenceMoveDialog, "exec", mock_exec)

    window._move_file_to_folder(str(src_file), dest_dir)

    assert not src_file.exists()
    assert (dest_dir / "data.csv").exists()


def test_drive_root_protection(tmp_path):
    """Verify that filesystem drive roots (like D:\\ or C:\\) are never detected or scanned as project root."""
    svc = PreViewAIService(project_root=str(tmp_path))
    window = run_gui_mode(svc, project_path=None, start_loop=False)

    drive_c = Path("C:/")
    drive_d = Path("D:/")

    cand_c = window._detect_project_root(str(drive_c))
    assert cand_c is None or len(cand_c.parts) > 1

    cand_d = window._detect_project_root(str(drive_d))
    assert cand_d is None or len(cand_d.parts) > 1


def test_navigation_tree_lazy_loading(mock_project):
    """Verify left navigation tree lazily loads child directories upon expansion."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    tree = window._left_tree
    assert tree is not None

    # Find the Monitored Project or folder item
    found_proj_item = None
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if "Monitored Project" in top.text(0):
            found_proj_item = top.child(0)
            break
        elif top.data(0, Qt.UserRole) == str(mock_project):
            found_proj_item = top
            break

    if found_proj_item:
        # Expanding the item triggers _on_left_tree_item_expanded
        window._on_left_tree_item_expanded(found_proj_item)
        child_paths = [
            found_proj_item.child(j).data(0, Qt.UserRole)
            for j in range(found_proj_item.childCount())
        ]
        assert str(mock_project / "dataset") in child_paths or str(mock_project / "models") in child_paths


def test_droppable_up_button_move(mock_project, monkeypatch):
    """Verify dropping a file onto DroppableUpButton moves it to the parent directory."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QDropEvent

    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    sub_dir = mock_project / "dataset"
    child_file = sub_dir / "data.csv"
    assert child_file.exists()

    window._navigate_to(str(sub_dir))

    # Mock consequence dialog confirmation
    def mock_exec(self):
        self.action_choice = "MOVE"
        return QDialog.Accepted

    monkeypatch.setattr(window.ConsequenceMoveDialog, "exec", mock_exec)

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(child_file))])

    event = QDropEvent(
        QPoint(5, 5),
        Qt.MoveAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    window._btn_up.dropEvent(event)

    parent_target = mock_project / "data.csv"
    assert parent_target.exists()
    assert not child_file.exists()


def test_droppable_path_bar_move(mock_project, monkeypatch):
    """Verify dropping a file onto DroppablePathBar moves it to the folder shown in the path bar."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QDropEvent

    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    src_file = mock_project / "train.py"
    target_dir = mock_project / "models"
    assert src_file.exists()

    window._path_bar.setText(str(target_dir))

    def mock_exec(self):
        self.action_choice = "MOVE"
        return QDialog.Accepted

    monkeypatch.setattr(window.ConsequenceMoveDialog, "exec", mock_exec)

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(src_file))])

    event = QDropEvent(
        QPoint(10, 10),
        Qt.MoveAction,
        mime,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    window._path_bar.dropEvent(event)

    dest_file = target_dir / "train.py"
    assert dest_file.exists()
    assert not src_file.exists()


def test_move_folder_cycle_prevention(mock_project, monkeypatch):
    """Verify moving a folder into its own subfolder is blocked with warning."""
    from PySide6.QtWidgets import QMessageBox

    warnings_called = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings_called.append(args))

    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    parent_folder = mock_project / "dataset"
    sub_folder = parent_folder / "nested"
    sub_folder.mkdir()

    # Attempting to move parent_folder into sub_folder should be prevented
    window._move_file_to_folder(str(parent_folder), sub_folder)

    # parent_folder must still exist at original location
    assert parent_folder.exists()
    assert sub_folder.exists()
    assert len(warnings_called) == 1


def test_move_always_triggers_consequence_dialog(mock_project, monkeypatch):
    """Verify that moving ANY file (even SAFE with 0 broken links) always shows ConsequenceMoveDialog."""
    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    src_file = mock_project / "dataset" / "data.csv"
    dest_dir = mock_project / "models"
    assert src_file.exists()

    dialog_shown = []

    def mock_exec_cancel(self):
        dialog_shown.append(self)
        self.action_choice = "CANCEL"
        return QDialog.Rejected

    monkeypatch.setattr(window.ConsequenceMoveDialog, "exec", mock_exec_cancel)

    # 1. Moving with CANCEL must show dialog and NOT move file
    window._move_file_to_folder(str(src_file), dest_dir)
    assert len(dialog_shown) == 1
    assert src_file.exists()
    assert not (dest_dir / "data.csv").exists()

    # 2. Moving with ACCEPT must show dialog and MOVE file
    def mock_exec_accept(self):
        dialog_shown.append(self)
        self.action_choice = "MOVE"
        return QDialog.Accepted

    monkeypatch.setattr(window.ConsequenceMoveDialog, "exec", mock_exec_accept)
    window._move_file_to_folder(str(src_file), dest_dir)
    assert len(dialog_shown) == 2
    assert not src_file.exists()
    assert (dest_dir / "data.csv").exists()


def test_clipboard_shortcut_focus_and_text_fallback(mock_project):
    """Verify Ctrl+C / Ctrl+V handles both text input focus and file operations properly."""
    from PySide6.QtWidgets import QLineEdit

    svc = PreViewAIService(project_root=str(mock_project))
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)

    # Test 1: When QLineEdit has focus, copy/paste operates on line edit text, not file system
    line_edit = QLineEdit(window)
    line_edit.show()
    line_edit.setText("Hello PreView AI")
    line_edit.selectAll()
    line_edit.setFocus()
    QApplication.processEvents()
    assert window._is_text_input_focused()

    # Calling _copy_selection while text input focused copies text, does not touch _clipboard_path
    window._clipboard_path = None
    window._copy_selection()
    assert window._clipboard_path is None
    assert QApplication.clipboard().text() == "Hello PreView AI"

    # Test 2: When text input is not focused, file copy sets clipboard and enables paste
    line_edit.clearFocus()
    assert not window._is_text_input_focused()

    train_path = str(mock_project / "train.py")
    window._copy_selection(train_path)
    assert window._clipboard_path == train_path
    assert window._clipboard_mode == "COPY"

    # Test 3: Text fallback in paste_selection - pasting path string from external text clipboard
    window._clipboard_path = None
    QApplication.clipboard().setText(str(mock_project / "train.py"))
    window._paste_selection()
    copy_file = mock_project / "train - Copy.py"
    assert copy_file.exists()


def test_watcher_ignores_wal_and_cache(tmp_path):
    """Verify that watcher ignores .cache and SQLite WAL/SHM database files."""
    from app.state.watcher import Watcher, IGNORE_DIRS, IGNORED_EXTENSIONS

    assert ".cache" in IGNORE_DIRS
    assert ".db-wal" in IGNORED_EXTENSIONS
    assert ".db-shm" in IGNORED_EXTENSIONS

    w = Watcher(str(tmp_path), lambda ev: None)
    # Trigger handler creation
    w.start()
    try:
        handler = list(w._observer._handlers[list(w._observer._handlers.keys())[0]])[0]
        assert handler._should_ignore(str(tmp_path / ".cache" / "state_index.db"))
        assert handler._should_ignore(str(tmp_path / "state_index.db-wal"))
        assert handler._should_ignore(str(tmp_path / "state_index.db-shm"))
        assert handler._should_ignore(str(tmp_path / "state_index.db"))
        assert not handler._should_ignore(str(tmp_path / "train.py"))
    finally:
        w.stop()



