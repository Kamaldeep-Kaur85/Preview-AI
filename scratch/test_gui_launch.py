import sys
from pathlib import Path
sys.path.insert(0, r"D:\preview ai")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from app.main import PreViewAIService, run_gui_mode

print("============================================================")
print(" TESTING PREVIEW AI REAL GUI STARTUP")
print("============================================================")

svc = PreViewAIService(project_root=r"D:\preview ai")

def on_timer():
    print("\n--- QTimer inspection after GUI start ---", flush=True)
    # Find the PreViewWindow instance
    win = None
    for top in QApplication.topLevelWidgets():
        if "PreViewWindow" in type(top).__name__:
            win = top
            break
    
    if win is None:
        print("[FAIL] PreViewWindow not found in topLevelWidgets!", flush=True)
        QApplication.quit()
        sys.exit(1)

    print(f"[PASS] PreViewWindow found: {win}", flush=True)
    print(f"       Window title: '{win.windowTitle()}'", flush=True)
    print(f"       Window isVisible: {win.isVisible()}", flush=True)
    print(f"       Window size: {win.size().width()}x{win.size().height()}", flush=True)
    
    # Check _show_context_menu
    has_menu = hasattr(win, "_show_context_menu") and callable(win._show_context_menu)
    print(f"       Has _show_context_menu: {has_menu}", flush=True)
    assert has_menu, "PreViewWindow missing _show_context_menu!"
    
    # Check key panels exist and are not removed
    assert hasattr(win, "_ai_page_widget"), "AI panel missing!"
    assert hasattr(win, "_preview_text") or hasattr(win, "_preview_widget") or hasattr(win, "_right_stack"), "Preview panel missing!"
    assert hasattr(win, "_graph_text"), "Graph panel missing!"
    assert hasattr(win, "_file_view"), "File Explorer missing!"
    assert hasattr(win, "_center_tabs"), "Center tabs missing!"
    print("[PASS] All required panels verified intact (AI panel, Preview panel, Graph, File Explorer, Simulate)!", flush=True)
    
    print("\n[SUCCESS] GUI INITIALIZATION AND STARTUP VERIFIED!", flush=True)
    print("Closing GUI cleanly...", flush=True)
    win.close()
    QApplication.quit()

# Set single shot timer to fire after 3.5 seconds to let UI finish initial layout
QTimer.singleShot(3500, on_timer)

print("Starting PreView AI GUI event loop...", flush=True)
# This calls run_gui_mode with start_loop=True, exactly like production
run_gui_mode(svc, project_path=r"D:\preview ai", start_loop=True)
print("GUI event loop exited cleanly.")
