import os
import sys
from pathlib import Path
import tempfile

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from app.main import PreViewAIService, run_gui_mode

with tempfile.TemporaryDirectory() as td:
    proj = Path(td) / "my_project"
    proj.mkdir()
    (proj / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
    (proj / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")
    ds_dir = proj / "dataset"
    ds_dir.mkdir()
    (ds_dir / "data.csv").write_text("id,val\n1,10", encoding="utf-8")
    sub_dir = proj / "models"
    sub_dir.mkdir()

    print("Step 1: Creating service", flush=True)
    svc = PreViewAIService(project_root=str(proj))

    # Test what happens if we patch PreViewWindow._start_scan
    # In run_gui_mode, let's see:
