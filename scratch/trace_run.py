import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import tempfile
import traceback

def trace_calls(frame, event, arg):
    if event == 'exception':
        print(f"EXCEPTION at line {frame.f_lineno} in {frame.f_code.co_filename}: {arg}")
    return trace_calls

sys.settrace(trace_calls)

try:
    tmp_path = Path(tempfile.mkdtemp())
    mock_project = tmp_path / "my_project"
    mock_project.mkdir()
    (mock_project / "train.py").write_text("import dataset", encoding="utf-8")

    svc = PreViewAIService(project_root=str(mock_project))
    print("Calling run_gui_mode...")
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
    print("Window created successfully:", window)
except BaseException as e:
    print(f"MAIN CAUGHT: {type(e)}: {e}")
    traceback.print_exc()
