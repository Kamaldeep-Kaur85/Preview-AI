import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")
import os

# DO NOT set offscreen, let's see what happens or test with default platform
from app.main import PreViewAIService, run_gui_mode
import tempfile

tmp_path = Path(tempfile.mkdtemp())
mock_project = tmp_path / "my_project"
mock_project.mkdir()
(mock_project / "train.py").write_text("import dataset", encoding="utf-8")

svc = PreViewAIService(project_root=str(mock_project))

print("1. Service created", flush=True)

try:
    print("2. Calling run_gui_mode...", flush=True)
    # We pass start_loop=False
    win = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
    print("3. run_gui_mode returned window:", win, flush=True)
except Exception as e:
    import traceback
    print("3. CAUGHT EXCEPTION:", e, flush=True)
    traceback.print_exc()
except BaseException as be:
    import traceback
    print("3. CAUGHT BASE EXCEPTION:", be, flush=True)
    traceback.print_exc()
finally:
    print("4. In finally block!", flush=True)
