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

    def close_all_menus():
        print("Timer fired!", flush=True)
        found = False
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMenu):
                print(f"Hiding QMenu {w}", flush=True)
                w.hide()
                found = True
        print(f"Menus found: {found}", flush=True)

    QTimer.singleShot(50, close_all_menus)
    print("Calling _show_context_menu...", flush=True)
    win._show_context_menu(QPoint(10, 10))
    print("Returned from _show_context_menu successfully!", flush=True)
except Exception as e:
    print(f"Exception: {e}", flush=True)
    traceback.print_exc()
finally:
    os._exit(0)
