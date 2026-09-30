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

    svc = PreViewAIService(project_root=str(proj))
    print("PreViewAIService loaded", flush=True)

    # Let's see what happens if we call load_project on svc directly!
    print("Calling svc.load_project(str(proj))...", flush=True)
    svc.load_project(str(proj))
    print("svc.load_project done!", flush=True)
