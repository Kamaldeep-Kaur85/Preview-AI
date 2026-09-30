import os
import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from app.main import PreViewAIService, run_gui_mode
import tempfile

print("Step 1: Creating mock project...", flush=True)
tmp_path = Path(tempfile.mkdtemp())
mock_project = tmp_path / "my_project"
mock_project.mkdir()
(mock_project / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
(mock_project / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")
ds_dir = mock_project / "dataset"
ds_dir.mkdir()
(ds_dir / "data.csv").write_text("id,val\n1,10", encoding="utf-8")

print("Step 2: Instantiating service...", flush=True)
svc = PreViewAIService(project_root=str(mock_project))

print("Step 3: Calling run_gui_mode...", flush=True)
window = run_gui_mode(svc, project_path=str(mock_project), start_loop=False)
print("Step 3: Done calling run_gui_mode!", flush=True)

print("Step 4: Processing events...", flush=True)
app.processEvents()

print("Step 5: Updating action bar state...", flush=True)
window._selected_path = None
window._update_action_bar_state()

print("Step 6: Checking action bar buttons...", flush=True)
assert not window._btn_cut.isEnabled()
assert not window._btn_copy.isEnabled()
assert not window._btn_rename.isEnabled()
assert not window._btn_delete.isEnabled()
assert not window._btn_sim_act.isEnabled()
assert not window._btn_paste.isEnabled()
print("Step 6: Action bar assertions passed!", flush=True)

print("Step 7: Checking dataset index...", flush=True)
ds_path = str(mock_project / "dataset")
idx = window._fs_model.index(ds_path)
print(f"Step 7: idx.isValid() = {idx.isValid()}", flush=True)
assert idx.isValid()

print("Step 8: Calling _on_file_clicked...", flush=True)
window._file_view.setCurrentIndex(idx)
window._on_file_clicked(idx)

print("Step 9: Checking selected buttons...", flush=True)
print(f"btn_cut: {window._btn_cut.isEnabled()}", flush=True)
print(f"btn_copy: {window._btn_copy.isEnabled()}", flush=True)
print(f"btn_rename: {window._btn_rename.isEnabled()}", flush=True)
print(f"btn_delete: {window._btn_delete.isEnabled()}", flush=True)
print(f"btn_sim_act: {window._btn_sim_act.isEnabled()}", flush=True)

assert window._btn_cut.isEnabled()
assert window._btn_copy.isEnabled()
assert window._btn_rename.isEnabled()
assert window._btn_delete.isEnabled()
assert window._btn_sim_act.isEnabled()

print("Step 10: Cleaning up workers...", flush=True)
if window._scan_worker and window._scan_worker.isRunning():
    window._scan_worker.wait(5000)
if window._impact_worker and window._impact_worker.isRunning():
    window._impact_worker.wait(5000)

window.close()
app.processEvents()

print("ALL STEPS COMPLETED SUCCESSFULLY!", flush=True)
