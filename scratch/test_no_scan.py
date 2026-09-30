import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService

print("Creating PreViewAIService...", flush=True)
svc = PreViewAIService(project_root=r"D:\preview ai")

# Import the class definition from run_gui_mode
# Let's inspect run_gui_mode line by line
print("Importing run_gui_mode...", flush=True)
from app.main import run_gui_mode

print("Testing run_gui_mode with project_path=None, start_loop=False...", flush=True)
try:
    # Disable start_scan by passing project_path=None or testing window directly
    win = run_gui_mode(svc, project_path=None, start_loop=False)
    print("WIN CREATED:", win, flush=True)
except BaseException as e:
    import traceback
    traceback.print_exc()
