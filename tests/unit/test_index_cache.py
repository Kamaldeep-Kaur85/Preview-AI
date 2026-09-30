"""
tests/unit/test_index_cache.py

Unit tests for app/state/index_cache.py:
- SQLite persistence of file metadata and parsed dependency edges
- Cache hit/miss checks based on mtime and size
- Schema migration handling
- Edge querying and deletion
"""
import time
from pathlib import Path
from app.state.index_cache import IndexCache


def test_index_cache_file_lifecycle(tmp_path):
    db_file = tmp_path / "cache.db"
    cache = IndexCache(db_file)

    test_path = str(tmp_path / "script.py")
    mtime = 1700000000.0
    size = 1024

    # Initially not cached
    assert cache.is_file_cached(test_path, mtime, size) is False

    # Upsert file without analysis
    cache.upsert_file(
        path=test_path,
        name="script.py",
        node_type="SCRIPT",
        size_bytes=size,
        mtime=mtime,
        extension=".py",
        analysis_done=False,
    )
    assert cache.is_file_cached(test_path, mtime, size) is False

    # Mark analyzed
    cache.mark_file_analyzed(test_path)
    assert cache.is_file_cached(test_path, mtime, size) is True

    # If mtime or size changes, cache misses
    assert cache.is_file_cached(test_path, mtime + 5.0, size) is False
    assert cache.is_file_cached(test_path, mtime, size + 10) is False

    # Check files list
    all_files = cache.get_all_files()
    assert len(all_files) == 1
    assert all_files[0]["path"] == test_path

    # Delete file
    cache.delete_file(test_path)
    assert len(cache.get_all_files()) == 0

    cache.close()


def test_index_cache_edge_operations(tmp_path):
    db_file = tmp_path / "cache.db"
    cache = IndexCache(db_file)

    src = "/path/to/main.py"
    tgt = "/path/to/utils.py"

    cache.upsert_edge(
        source=src,
        target=tgt,
        edge_type="IMPORTS",
        confidence="CONFIRMED",
        method="ast_import",
        line_number=10,
        raw_text="import utils",
    )
    cache.commit()

    edges_from = cache.get_edges_from(src)
    assert len(edges_from) == 1
    assert edges_from[0]["target"] == tgt
    assert edges_from[0]["edge_type"] == "IMPORTS"

    edges_to = cache.get_edges_to(tgt)
    assert len(edges_to) == 1
    assert edges_to[0]["source"] == src

    # Test idempotence (no duplicates)
    cache.upsert_edge(
        source=src,
        target=tgt,
        edge_type="IMPORTS",
        confidence="CONFIRMED",
        method="ast_import",
    )
    assert len(cache.get_all_edges()) == 1

    cache.delete_edges_from(src)
    assert len(cache.get_edges_from(src)) == 0

    cache.close()


def test_index_cache_project_metadata_and_stats(tmp_path):
    db_file = tmp_path / "cache.db"
    cache = IndexCache(db_file)

    cache.set_project_root(str(tmp_path))
    assert cache.get_project_root() == str(tmp_path)

    stats = cache.get_stats()
    assert stats["total_files"] == 0
    assert stats["total_edges"] == 0
    assert stats["last_scan"] > 0

    cache.close()
