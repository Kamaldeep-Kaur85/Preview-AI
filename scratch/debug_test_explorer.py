import os
import sys
from pathlib import Path
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

print("1. Start script")
from tests.unit.test_explorer_operations import test_selection_enables_action_buttons
print("2. Imported test_selection_enables_action_buttons")

import tempfile
with tempfile.TemporaryDirectory() as td:
    print("3. Inside tempdir:", td)
    proj = Path(td) / "my_project"
    proj.mkdir()
    (proj / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
    (proj / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")
    ds_dir = proj / "dataset"
    ds_dir.mkdir()
    (ds_dir / "data.csv").write_text("id,val\n1,10", encoding="utf-8")
    sub_dir = proj / "models"
    sub_dir.mkdir()
    print("4. Project structure created")

    print("5. Calling test_selection_enables_action_buttons(proj)")
    test_selection_enables_action_buttons(proj)
    print("6. Returned from test_selection_enables_action_buttons")
