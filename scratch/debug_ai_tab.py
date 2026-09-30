import os
import sys
import traceback
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
from app.main import PreViewAIService, run_gui_mode

tmp_path = Path(r"D:\preview ai\scratch\ai_test_tmp")
tmp_path.mkdir(exist_ok=True)

app_py = tmp_path / "app.py"
app_py.write_text("import joblib\nmodel = joblib.load('model.pkl')\n", encoding="utf-8")
model_pkl = tmp_path / "model.pkl"
model_pkl.write_text("pickle-dummy", encoding="utf-8")

svc = PreViewAIService(project_root=str(tmp_path))
svc.load_project(str(tmp_path))

window = run_gui_mode(svc, project_path=None, start_loop=False)
try:
    window._selected_path = str(model_pkl)
    window._ai_input.setText("what happens if action performed")
    window._send_ai_message()

    chat = window._ai_chat.toPlainText()
    print("CHAT 1:\n", chat, flush=True)
    assert "Consequence Analysis" in chat
    assert "model.pkl" in chat

    window._ai_input.setText("what uses model.pkl?")
    window._send_ai_message()
    chat = window._ai_chat.toPlainText()
    print("CHAT 2:\n", chat, flush=True)
    assert "model.pkl" in chat
    assert "app.py" in chat

    window._ai_input.setText("explain this project")
    window._send_ai_message()
    chat = window._ai_chat.toPlainText()
    print("CHAT 3:\n", chat, flush=True)
    assert "Project Architecture Overview" in chat

    window._update_graph_tab()
    graph_html = window._graph_text.toHtml()
    graph_text = window._graph_text.toPlainText()
    print("GRAPH TEXT:\n", graph_text, flush=True)
    assert "Project Architecture" in graph_html
    assert "WORKFLOW & DATA PIPELINE" in graph_text or ("WORKFLOW" in graph_html and "DATA PIPELINE" in graph_html)
    print("ALL PASSED IN TEST SCRIPT!")
except Exception as e:
    print(f"FAILED: {e}")
    traceback.print_exc()
finally:
    window._service.stop_watcher()
    window.close()
    os._exit(0)
