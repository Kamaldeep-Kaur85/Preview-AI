import os
import sys

def pytest_unconfigure(config):
    """
    Prevent Windows PySide6 / Python 3.13 C++ static destructor abort (0xC0000409)
    upon clean process exit during headless Qt test runs.
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os._exit(0)
