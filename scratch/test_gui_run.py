import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import traceback
import faulthandler

faulthandler.enable()

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import tempfile

tmp_path = Path(tempfile.mkdtemp())
mock_project = tmp_path / "my_project"
mock_project.mkdir()
(mock_project / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
(mock_project / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")
ds_dir = mock_project / "dataset"
ds_dir.mkdir()
(ds_dir / "data.csv").write_text("id,val\n1,10", encoding="utf-8")

print("Created mock project at:", mock_project)
svc = PreViewAIService(project_root=str(mock_project))
print("Created PreViewAIService")

try:
    print("About to call run_gui_mode...")
    window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
    print("SUCCESS! run_gui_mode returned window:", window)

    # Allow Qt events to process
    app.processEvents()

    # Test file click and context menu call
    print("Testing context menu request...")
    from PySide6.QtCore import QPoint
    window._show_context_menu(QPoint(10, 10))
    print("Context menu called successfully!")

    # Clean up
    if window._scan_worker and window._scan_worker.isRunning():
        window._scan_worker.wait(2000)
    if window._impact_worker and window._impact_worker.isRunning():
        window._impact_worker.wait(2000)
    window.close()
    app.processEvents()
    print("ALL TESTS PASSED CLEANLY!")
except Exception as e:
    print("CAUGHT EXCEPTION:")
    traceback.print_exc()
    sys.exit(1)
