import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import tempfile

tmp_path = Path(tempfile.mkdtemp())
mock_project = tmp_path / "my_project"
mock_project.mkdir()
(mock_project / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")

svc = PreViewAIService(project_root=str(mock_project))

last_line = None
last_func = None
def tracer(frame, event, arg):
    global last_line, last_func
    if "main.py" in frame.f_code.co_filename:
        if event == "line":
            last_line = frame.f_lineno
            last_func = frame.f_code.co_name
        elif event == "exception":
            print(f"EXCEPTION at line {frame.f_lineno} in {frame.f_code.co_name}: {arg}", flush=True)
    return tracer

sys.settrace(tracer)

import atexit
def on_exit():
    print(f"ATEXIT: last executed in main.py was function '{last_func}' at line {last_line}", flush=True)

atexit.register(on_exit)

print("About to call run_gui_mode...", flush=True)
window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
print("Finished run_gui_mode successfully!", flush=True)
