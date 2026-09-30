import os
import sys
from pathlib import Path
import tempfile
import traceback

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from tests.unit.test_explorer_operations import test_watcher_ignores_wal_and_cache

with tempfile.TemporaryDirectory() as td:
    try:
        test_watcher_ignores_wal_and_cache(Path(td))
        print("SUCCESS!", flush=True)
    except Exception as e:
        traceback.print_exc()
