import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

from app.main import PreViewAIService

svc = PreViewAIService(project_root=r"D:\preview ai")
svc.load_project(r"D:\preview ai")

print("Calling simulate_intent('modify app/main.py')...", flush=True)
ok, msg, data = svc.simulate_intent("modify app/main.py")
print(f"ok={ok}, msg={msg}, data={data.keys() if data else None}", flush=True)
if ok:
    impact = data.get("impact")
    print(f"impact risk={impact.risk.value}, affected={len(impact.affected_files)}", flush=True)
