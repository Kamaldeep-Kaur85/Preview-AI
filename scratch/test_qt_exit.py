import os
import sys
import atexit

atexit.register(lambda: print("AT EXIT HANDLER CALLED", flush=True))

print("Script running...", flush=True)
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
print("QApplication initialized", flush=True)
