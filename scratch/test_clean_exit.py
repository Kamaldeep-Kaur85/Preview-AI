import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode

print("Creating PreViewAIService...", flush=True)
svc = PreViewAIService(project_root=r"D:\preview ai")

print("Testing run_gui_mode with project_path=None, start_loop=False...", flush=True)
win = run_gui_mode(svc, project_path=None, start_loop=False)
print("WIN CREATED:", win, flush=True)

# Test context menu method exists and is callable
assert hasattr(win, "_show_context_menu")
print("Confirmed win._show_context_menu exists!", flush=True)

# Close cleanly
win.close()
app.processEvents()
print("SUCCESS - EXITING WITH 0", flush=True)
os._exit(0)
