import os
import sys
from pathlib import Path
import tempfile

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from PySide6.QtWidgets import QApplication, QLineEdit
from app.main import PreViewAIService, run_gui_mode

with tempfile.TemporaryDirectory() as td:
    proj = Path(td) / "my_project"
    proj.mkdir()
    (proj / "train.py").write_text("import dataset\nprint('training...')", encoding="utf-8")
    (proj / "app.py").write_text("import dataset\nimport train\nprint('running app...')", encoding="utf-8")

    svc = PreViewAIService(project_root=str(proj))
    window = run_gui_mode(svc, project_path=str(proj), start_loop=False)

    print("Running Part 1: focus check", flush=True)
    line_edit = QLineEdit(window)
    line_edit.setText("Hello PreView AI")
    line_edit.selectAll()
    line_edit.setFocus()
    print("Focused:", window._is_text_input_focused(), flush=True)

    window._clipboard_path = None
    window._copy_selection()
    print("Clipboard text:", QApplication.clipboard().text(), flush=True)

    print("Running Part 2: clear focus", flush=True)
    line_edit.clearFocus()
    print("Focused after clear:", window._is_text_input_focused(), flush=True)
    train_path = str(proj / "train.py")
    window._copy_selection(train_path)
    print("Clipboard path:", window._clipboard_path, "mode:", window._clipboard_mode, flush=True)

    print("Running Part 3: text fallback", flush=True)
    window._clipboard_path = None
    QApplication.clipboard().setText(str(proj / "train.py"))
    print("Calling _paste_selection...", flush=True)
    window._paste_selection()
    copy_file = proj / "train - Copy.py"
    print("Copy file exists:", copy_file.exists(), flush=True)

    window.close()
    print("SUCCESS!", flush=True)
