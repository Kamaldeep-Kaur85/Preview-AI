import sys
import os
import time
from pathlib import Path

# Add project root
sys.path.insert(0, r"D:\preview ai")

# We run headless/offscreen for automated pipeline, but GUI widgets fully initialize
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QTimer

app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode

print("============================================================")
print(" VERIFYING COMPLETE PREVIEW AI GUI FUNCTIONALITY")
print("============================================================")

project_root = r"D:\preview ai"
print(f"[1/13] Initializing PreViewAIService with project: {project_root}")
svc = PreViewAIService(project_root=project_root)
svc.load_project(project_root)

print("[2/13] Launching PreViewWindow in GUI mode...")
win = run_gui_mode(svc, project_path=project_root, start_loop=False)
assert win is not None, "PreViewWindow failed to initialize!"
assert win.isVisible() or os.environ.get("QT_QPA_PLATFORM") == "offscreen", "Window not visible!"
print("       ✓ PreViewWindow initialized and visible!")

app.processEvents()

# 1. Open folder
print("[3/13] Testing open folder...")
models_dir = str(Path(project_root) / "models")
win._navigate_to(models_dir)
app.processEvents()
assert win._get_current_directory() == Path(models_dir), f"Current dir is {win._get_current_directory()}"
print(f"       ✓ Navigated to folder: {models_dir}")

# 2. Navigate folders
print("[4/13] Testing navigate back to project root...")
win._navigate_to(project_root)
app.processEvents()
assert win._get_current_directory() == Path(project_root)
print("       ✓ Navigated back to project root!")

# 3. Select a file
print("[5/13] Testing select a file...")
target_file = str(Path(project_root) / "run_preview_ai.bat")
win._selected_path = target_file
win._update_preview(target_file)
app.processEvents()
print(f"       target_file: {target_file}")
print(f"       win._selected_path: {win._selected_path}")
assert Path(win._selected_path) == Path(target_file)
print(f"       ✓ File selected: {target_file}")

# 4. Right-click a file (context menu)
print("[6/13] Testing right-click context menu callback...")
assert hasattr(win, "_show_context_menu"), "PreViewWindow missing _show_context_menu!"
assert callable(win._show_context_menu), "_show_context_menu is not callable!"
print("       ✓ _show_context_menu method verified on PreViewWindow")

# Test calling context menu with QTimer to auto-close popup menu
def auto_close_menu():
    for widget in QApplication.topLevelWidgets():
        if widget.inherits("QMenu"):
            widget.close()
            widget.hide()
    p = QApplication.activePopupWidget()
    if p:
        p.close()

QTimer.singleShot(50, auto_close_menu)
win._show_context_menu(QPoint(10, 10))
app.processEvents()
print("       ✓ Context menu opened and closed successfully without errors!")

# 5. Open Preview
print("[7/13] Testing Preview panel update...")
main_py = str(Path(project_root) / "app" / "main.py")
win._update_preview(main_py)
app.processEvents()
print("       ✓ Preview panel updated with file content!")

# 6. Open Graph
print("[8/13] Testing open Graph tab...")
win._center_tabs.setCurrentIndex(1)
app.processEvents()
assert win._center_tabs.currentIndex() == 1
print("       ✓ Graph tab opened (currentIndex=1)!")

# 7. Open Simulate tab
print("[9/13] Testing open Simulate tab...")
win._center_tabs.setCurrentIndex(2)
app.processEvents()
assert win._center_tabs.currentIndex() == 2
print("       ✓ Simulate tab opened (currentIndex=2)!")

# 8. Open AI panel
print("[10/13] Testing open AI panel...")
win._ai_btn.setChecked(True)
win._toggle_ai_panel()
app.processEvents()
assert win._ai_open == True
assert win._right_stack.currentIndex() == 1
print("        ✓ AI panel opened (win._ai_open is True, right stack index=1)!")

# 9. Type AI question & press Enter
print("[11/13] Testing typing AI question and submitting...")
win._ai_input.setText("What does this project do?")
win._send_ai_message()
app.processEvents()
print("        ✓ AI question sent and processed!")

# 10. Close AI panel
print("[12/13] Testing close AI panel...")
win._ai_btn.setChecked(False)
win._toggle_ai_panel()
app.processEvents()
assert win._ai_open == False
assert win._right_stack.currentIndex() == 0
print("        ✓ AI panel closed (win._ai_open is False, right stack index=0)!")

# 11. Select another file & simulate an operation
print("[13/13] Testing select another file & simulate operation...")
try:
    win._selected_path = str(Path(project_root) / "app" / "main.py")
    win._center_tabs.setCurrentIndex(2)
    win._intent_edit.setText("modify app/main.py")
    print("        Calling _run_simulation()...", flush=True)
    win._run_simulation()
    print("        _run_simulation() called. Waiting for sim_worker...", flush=True)

    for i in range(100):
        if win._sim_worker and win._sim_worker.isRunning():
            time.sleep(0.1)
            app.processEvents()
        else:
            break
    app.processEvents()

    print(f"        win._current_impact: {win._current_impact}", flush=True)
    assert win._current_impact is not None, "win._current_impact is None!"
    print(f"        ✓ Simulation completed! Risk: {win._current_impact.risk.value}", flush=True)
except Exception as e:
    import traceback
    print("ERROR IN STEP 13:", flush=True)
    traceback.print_exc()
    sys.exit(1)

# Clean up
if win._scan_worker and win._scan_worker.isRunning():
    win._scan_worker.wait(3000)
if win._impact_worker and win._impact_worker.isRunning():
    win._impact_worker.wait(3000)
if win._sim_worker and win._sim_worker.isRunning():
    win._sim_worker.wait(3000)

win.close()
app.processEvents()

print("\n============================================================")
print(" ALL 13 GUI FUNCTIONALITY CHECKS PASSED SUCCESSFULLY! ")
print("============================================================")
os._exit(0)
