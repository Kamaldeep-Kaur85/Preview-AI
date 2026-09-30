import sys
import os
import traceback
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtCore import Qt, QPoint, QTimer

app = QApplication.instance() or QApplication(sys.argv)
from app.main import PreViewAIService, run_gui_mode

try:
    svc = PreViewAIService(project_root=r"D:\preview ai")
    win = run_gui_mode(svc, project_path=None, start_loop=False)

    print("Step 1: Init OK", flush=True)

    print("Step 2: Navigate folder", flush=True)
    models_dir = str(Path(r"D:\preview ai") / "models")
    win._navigate_to(models_dir)
    app.processEvents()

    print("Step 3: Navigate root", flush=True)
    win._navigate_to(r"D:\preview ai")
    app.processEvents()

    print("Step 4: Select file", flush=True)
    target_file = str(Path(r"D:\preview ai") / "run_preview_ai.bat")
    win._selected_path = target_file
    win._update_preview(target_file)
    app.processEvents()

    print("Step 5: Show context menu", flush=True)
    def close_menus():
        print("Closing menus timer fired...", flush=True)
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMenu):
                w.hide()
    QTimer.singleShot(100, close_menus)
    win._show_context_menu(QPoint(10, 10))
    app.processEvents()
    print("Step 5 OK", flush=True)

    print("Step 6: Open Preview", flush=True)
    main_py = str(Path(r"D:\preview ai") / "app" / "main.py")
    win._update_preview(main_py)
    app.processEvents()

    print("Step 7: Open Graph", flush=True)
    win._center_tabs.setCurrentIndex(1)
    app.processEvents()

    print("Step 8: Open Simulate", flush=True)
    win._center_tabs.setCurrentIndex(2)
    app.processEvents()

    print("Step 9: Open AI", flush=True)
    win._ai_btn.setChecked(True)
    win._toggle_ai_panel()
    app.processEvents()

    print("Step 10: Send AI question", flush=True)
    win._ai_input.setText("What does this project do?")
    win._send_ai_message()
    app.processEvents()

    print("Step 11: Close AI", flush=True)
    win._ai_btn.setChecked(False)
    win._toggle_ai_panel()
    app.processEvents()

    print("Step 12: Select another file", flush=True)
    other_file = str(Path(r"D:\preview ai") / "README.md")
    win._selected_path = other_file
    win._update_preview(other_file)
    app.processEvents()

    print("Step 13: Simulate operation", flush=True)
    win._center_tabs.setCurrentIndex(2)
    win._intent_edit.setText("modify README.md")
    win._run_simulation()
    if win._sim_worker:
        win._sim_worker.wait(5000)
    app.processEvents()
    print("ALL STEPS FINISHED SUCCESS!", flush=True)
except Exception as e:
    print(f"Exception: {e}", flush=True)
    traceback.print_exc()
finally:
    try:
        win._service.stop_watcher()
        if hasattr(win, "_scan_worker") and win._scan_worker and win._scan_worker.isRunning():
            win._scan_worker.wait(1000)
        if hasattr(win, "_impact_worker") and win._impact_worker and win._impact_worker.isRunning():
            win._impact_worker.wait(1000)
        if hasattr(win, "_sim_worker") and win._sim_worker and win._sim_worker.isRunning():
            win._sim_worker.wait(1000)
        win.close()
    except Exception:
        pass
    os._exit(0)
