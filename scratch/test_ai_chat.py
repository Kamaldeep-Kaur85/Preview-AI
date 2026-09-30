import os
import sys
from pathlib import Path
import tempfile
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from app.main import PreViewAIService, run_gui_mode

with tempfile.TemporaryDirectory() as td:
    tmp_path = Path(td)
    app_py = tmp_path / "app.py"
    app_py.write_text("import joblib\nmodel = joblib.load('model.pkl')\n", encoding="utf-8")
    model_pkl = tmp_path / "model.pkl"
    model_pkl.write_text("pickle-dummy", encoding="utf-8")

    svc = PreViewAIService(project_root=str(tmp_path))
    svc.load_project(str(tmp_path))

    window = run_gui_mode(svc, project_path=None, start_loop=False)

    try:
        # Test 1: Action consequence query
        window._selected_path = str(model_pkl)
        window._ai_input.setText("what happens if action performed")
        window._send_ai_message()

        chat = window._ai_chat.toPlainText()
        print("CHAT 1:")
        print(chat)
        assert "Consequence Analysis" in chat
        assert "model.pkl" in chat
        print("TEST 1 PASSED!")

        # Test 2: Dependency query
        window._ai_input.setText("what uses model.pkl?")
        window._send_ai_message()
        chat = window._ai_chat.toPlainText()
        print("CHAT 2:")
        print(chat)
        assert "model.pkl" in chat
        assert "app.py" in chat
        print("TEST 2 PASSED!")

        # Test 3: Project explanation query
        window._ai_input.setText("explain this project")
        window._send_ai_message()
        chat = window._ai_chat.toPlainText()
        print("CHAT 3:")
        print(chat)
        assert "Project Architecture Overview" in chat
        print("TEST 3 PASSED!")

        # Test 4: Visual graph tab rendering
        window._update_graph_tab()
        graph_html = window._graph_text.toHtml()
        graph_text = window._graph_text.toPlainText()
        assert "Project Architecture" in graph_html
        assert "WORKFLOW & DATA PIPELINE" in graph_text or ("WORKFLOW" in graph_html and "DATA PIPELINE" in graph_html)
        print("TEST 4 PASSED!")

        print("ALL 4 PASSED!")
    except Exception as e:
        traceback.print_exc()
    finally:
        window.close()
