import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import tempfile
import traceback

tmp_path = Path(tempfile.mkdtemp())
mock_project = tmp_path / "my_project"
mock_project.mkdir()
(mock_project / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")

svc = PreViewAIService(project_root=str(mock_project))

try:
    print("Starting run_gui_mode...", flush=True)
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
    print("Window returned successfully:", window, flush=True)
    
    if window._scan_worker and window._scan_worker.isRunning():
        print("Waiting for scan worker to complete...", flush=True)
        window._scan_worker.wait(5000)
        print("Scan worker completed!", flush=True)
    
    if window._impact_worker and window._impact_worker.isRunning():
        print("Waiting for impact worker to complete...", flush=True)
        window._impact_worker.wait(5000)
        print("Impact worker completed!", flush=True)

    window.close()
    app.processEvents()
    print("ALL CLEANUP COMPLETED - CLEAN EXIT (0)!", flush=True)
except BaseException as e:
    print("EXCEPTION CAUGHT:", type(e), e, flush=True)
    traceback.print_exc()
    sys.exit(1)
