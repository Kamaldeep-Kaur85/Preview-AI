import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import traceback

svc = PreViewAIService(project_root=r"D:\preview ai")
win = run_gui_mode(svc, project_path=r"D:\preview ai", start_loop=False)

print("Testing direct simulation...", flush=True)
ok, msg, data = svc.simulate_intent("modify app/main.py")
print(f"simulate_intent: ok={ok}, msg={msg}", flush=True)

try:
    print("Calling _on_sim_done directly...", flush=True)
    win._on_sim_done(ok, msg, data)
    print("SUCCESS: _on_sim_done completed without error!", flush=True)
except Exception as e:
    print("EXCEPTION in _on_sim_done:")
    traceback.print_exc()

win.close()
app.processEvents()
os._exit(0)
