import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, r"D:\preview ai")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import Qt, QPoint, QTimer

app = QApplication.instance() or QApplication(sys.argv)
from app.main import PreViewAIService, run_gui_mode

test_file = Path(r"D:\preview ai\run_preview_ai.bat")

svc = PreViewAIService(project_root=r"D:\preview ai")
window = run_gui_mode(svc, project_path=None, start_loop=False)

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
print("All actions:", all_actions, flush=True)

assert any("Open" in t for t in all_actions)
assert any("Cut" in t for t in all_actions)
assert any("Copy" in t for t in all_actions)
assert any("Rename" in t for t in all_actions)
assert any("Delete" in t for t in all_actions)
assert any("Simulate Impact" in t for t in all_actions)
assert any("Show in Dependency Graph" in t for t in all_actions)
assert any("Ask PreView AI" in t for t in all_actions)
print("TEST FILE MENU SUCCESS!", flush=True)

# Now test blank space
captured_menus.clear()
from PySide6.QtCore import QModelIndex
invalid_idx = QModelIndex()

QTimer.singleShot(50, dismiss_and_capture)
with patch.object(window._file_view, "indexAt", return_value=invalid_idx):
    window._show_context_menu(QPoint(999, 999))

blank_actions = [a.text() for m in captured_menus for a in m.actions() if a.text()]
print("Blank actions:", blank_actions, flush=True)
assert any("New" in t for t in blank_actions)
assert any("Paste" in t for t in blank_actions)
assert any("Index Current Folder as Project" in t for t in blank_actions)
assert any("Refresh" in t for t in blank_actions)
print("TEST BLANK CANVAS SUCCESS!", flush=True)

window._service.stop_watcher()
window.close()
os._exit(0)
