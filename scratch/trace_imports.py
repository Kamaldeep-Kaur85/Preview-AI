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
    print("Calling run_gui_mode with project_path=None...", flush=True)
    window = run_gui_mode(svc, project_path=None, start_loop=False)
    print("Window created successfully with None!", flush=True)

print("Done!", flush=True)
