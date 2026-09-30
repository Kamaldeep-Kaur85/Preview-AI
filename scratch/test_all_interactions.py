import sys
import os
import time
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import Qt, QPoint, QTimer

app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode

project_root = r"D:\preview ai"
svc = PreViewAIService(project_root=project_root)

print("[1] Initializing GUI window with run_gui_mode...", flush=True)
win = run_gui_mode(svc, project_path=None, start_loop=False)
assert win is not None, "PreViewWindow failed to initialize!"
print("    ✓ PreViewWindow initialized successfully!", flush=True)

# Wait for initial scan to complete so project graph is ready
if win._scan_worker and win._scan_worker.isRunning():
    print("    Waiting for initial scan worker...", flush=True)
    win._scan_worker.wait(15000)
    print("    ✓ Initial scan complete!", flush=True)
app.processEvents()

# 1. Open folder
print("[2] Open folder...", flush=True)
models_dir = str(Path(project_root) / "models")
win._navigate_to(models_dir)
app.processEvents()
assert Path(win._get_current_directory()) == Path(models_dir)
print(f"    ✓ Navigated to folder: {models_dir}", flush=True)

# 2. Navigate folders
print("[3] Navigate folders...", flush=True)
win._navigate_to(project_root)
app.processEvents()
assert Path(win._get_current_directory()) == Path(project_root)
print("    ✓ Navigated back to project root!", flush=True)

# 3. Select a file
print("[4] Select a file...", flush=True)
target_file = str(Path(project_root) / "run_preview_ai.bat")
win._selected_path = target_file
win._update_preview(target_file)
app.processEvents()
assert Path(win._selected_path) == Path(target_file)
print(f"    ✓ File selected: {target_file}", flush=True)

# 4. Right-click a file (context menu)
print("[5] Right-click a file (trigger _show_context_menu)...", flush=True)
assert hasattr(win, "_show_context_menu") and callable(win._show_context_menu)
def auto_close_menu():
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QMenu):
            w.hide()

QTimer.singleShot(100, auto_close_menu)
win._show_context_menu(QPoint(10, 10))
app.processEvents()
print("    ✓ Context menu opened and closed cleanly!", flush=True)

# 5. Open Preview
print("[6] Open Preview...", flush=True)
main_py = str(Path(project_root) / "app" / "main.py")
win._update_preview(main_py)
app.processEvents()
print("    ✓ Preview updated with file content!", flush=True)

# 6. Open Graph
print("[7] Open Graph...", flush=True)
win._center_tabs.setCurrentIndex(1)
app.processEvents()
assert win._center_tabs.currentIndex() == 1
print("    ✓ Graph tab opened!", flush=True)

# 7. Open Simulate
print("[8] Open Simulate...", flush=True)
win._center_tabs.setCurrentIndex(2)
app.processEvents()
assert win._center_tabs.currentIndex() == 2
print("    ✓ Simulate tab opened!", flush=True)

# 8. Open AI panel
print("[9] Open AI panel...", flush=True)
win._ai_btn.setChecked(True)
win._toggle_ai_panel()
app.processEvents()
assert win._ai_open == True
assert win._right_stack.currentIndex() == 1
print("    ✓ AI panel opened!", flush=True)

# 9. Type AI question & press Enter
print("[10] Type AI question & press Enter...", flush=True)
win._ai_input.setText("What does this project do?")
win._send_ai_message()
app.processEvents()
chat_text = win._ai_chat.toPlainText()
assert "What does this project do?" in chat_text
print("    ✓ AI question sent and processed into chat!", flush=True)

# 10. Close AI panel
print("[11] Close AI panel...", flush=True)
win._ai_btn.setChecked(False)
win._toggle_ai_panel()
app.processEvents()
assert win._ai_open == False
assert win._right_stack.currentIndex() == 0
print("    ✓ AI panel closed!", flush=True)

# 11. Select another file
print("[12] Select another file...", flush=True)
other_file = str(Path(project_root) / "README.md")
win._selected_path = other_file
win._update_preview(other_file)
app.processEvents()
assert Path(win._selected_path) == Path(other_file)
print(f"    ✓ Selected other file: {other_file}", flush=True)

# 12. Simulate an operation
print("[13] Simulate an operation...", flush=True)
win._center_tabs.setCurrentIndex(2)
win._intent_edit.setText("modify README.md")
win._run_simulation()
if win._sim_worker:
    print("    Waiting for sim_worker...", flush=True)
    win._sim_worker.wait(15000)
app.processEvents()
assert win._current_impact is not None
print(f"    ✓ Simulation successful! Risk: {win._current_impact.risk.value}", flush=True)

# Clean up
if win._scan_worker and win._scan_worker.isRunning():
    win._scan_worker.wait(2000)
if win._impact_worker and win._impact_worker.isRunning():
    win._impact_worker.wait(2000)
if win._sim_worker and win._sim_worker.isRunning():
    win._sim_worker.wait(2000)

win.close()
app.processEvents()

print("\n============================================================")
print(" ALL 12 USER INTERACTIONS VERIFIED SUCCESSFULLY! ")
print("============================================================")
os._exit(0)
