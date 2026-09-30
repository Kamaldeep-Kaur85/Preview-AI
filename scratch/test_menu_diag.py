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
    print("PreViewWindow created", flush=True)

    # Let's test context menu creation directly
    def close_all_menus():
        print("Timer fired, closing menus...", flush=True)
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMenu):
                print(f"Closing QMenu {w}", flush=True)
                w.close()
        app.quit()

    QTimer.singleShot(100, close_all_menus)
    print("Calling _show_context_menu...", flush=True)
    win._show_context_menu(QPoint(10, 10))
    print("After _show_context_menu!", flush=True)
except Exception as e:
    print(f"Exception caught: {e}", flush=True)
    traceback.print_exc()
finally:
    print("Done test_menu_diag", flush=True)
    os._exit(0)
