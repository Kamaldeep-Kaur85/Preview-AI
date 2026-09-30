import os
import sys
from pathlib import Path
import tempfile
import time

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from app.state.index_cache import IndexCache
from app.graph.builder import GraphBuilder

with tempfile.TemporaryDirectory() as td:
    proj_dir = Path(td) / "incremental_project"
    proj_dir.mkdir()

    f1 = proj_dir / "auth.py"
    f1.write_text("def login(): pass\n", encoding="utf-8")

    f2 = proj_dir / "utils.py"
    f2.write_text("def helper(): return 42\n", encoding="utf-8")

    cache_db = proj_dir / ".preview_cache.db"
    cache = IndexCache(cache_db)

    builder = GraphBuilder(proj_dir, cache=cache)
    graph1 = builder.build()

    mtime1 = f1.stat().st_mtime
    mtime2 = f2.stat().st_mtime
    print("f1 cached initially:", cache.get_parsed_ast(str(f1), mtime1, f1.stat().st_size) is not None)

    time.sleep(0.05)
    f1.write_text("def login(): return 'v2'\ndef logout(): pass\n", encoding="utf-8")
    new_mtime1 = f1.stat().st_mtime

    builder.incremental_update_file(graph1, f1, "modified")

    print("f2 cached after update:", cache.get_parsed_ast(str(f2), mtime2, f2.stat().st_size) is not None)
    res = cache.get_parsed_ast(str(f1), new_mtime1, f1.stat().st_size)
    print("f1 cached after update:", res is not None)
    if res is None:
        # Check what is in the db for f1
        row = cache._conn.execute("SELECT mtime, size_bytes FROM parsed_ast").fetchall()
        print("Rows in parsed_ast:", [dict(r) for r in row])
        print("Expected mtime:", new_mtime1, "Expected size:", f1.stat().st_size)
