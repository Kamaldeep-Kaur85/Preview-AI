"""
app/state/index_cache.py

Persistent SQLite-backed state index.
Caches file analysis results so unchanged files are never re-parsed.

Schema:
    files:      path, mtime, size, node_type, analysis_done, analysis_ts
    edges:      source, target, edge_type, confidence, method, line_number, raw_text
    meta:       key, value (project root, last scan time, etc.)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("preview_ai.index_cache")

SCHEMA_VERSION = 3


class IndexCache:
    """
    SQLite-backed file analysis cache.
    Stores scanned nodes + edges so the app can restart without re-parsing.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._open()

    def _open(self):
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=3.0,
                isolation_level=None,  # Autocommit mode: prevent long-running exclusive locks
            )
            self._conn.row_factory = sqlite3.Row
            try:
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA busy_timeout=3000;")
            except Exception:
                pass
            self._ensure_schema()
        except sqlite3.OperationalError as e:
            logger.warning(f"IndexCache: database locked or unavailable ({e}); running in safe fallback mode.")

    def _ensure_schema(self):
        if not self._conn:
            return
        try:
            cur = self._conn.cursor()
            # Meta table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Files table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    path        TEXT PRIMARY KEY,
                    name        TEXT,
                    node_type   TEXT,
                    size_bytes  INTEGER,
                    mtime       REAL,
                    analysis_done INTEGER DEFAULT 0,
                    analysis_ts   REAL    DEFAULT 0,
                    extension   TEXT
                )
            """)
            # Edges table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source      TEXT,
                    target      TEXT,
                    edge_type   TEXT,
                    confidence  TEXT,
                    method      TEXT,
                    line_number INTEGER,
                    raw_text    TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target)")

            # Parsed AST cache for instant incremental lookups
            cur.execute("""
                CREATE TABLE IF NOT EXISTS parsed_ast (
                    path        TEXT PRIMARY KEY,
                    mtime       REAL,
                    size_bytes  INTEGER,
                    data_json   TEXT
                )
            """)

            # Check schema version
            version = self._get_meta("schema_version")
            if version != str(SCHEMA_VERSION):
                self._migrate(old_version=int(version) if version else 0)
                self._set_meta("schema_version", str(SCHEMA_VERSION))

            try:
                self._conn.commit()
            except Exception:
                pass
        except sqlite3.OperationalError as e:
            logger.warning(f"IndexCache: schema init skipped due to lock: {e}")

    def _migrate(self, old_version: int):
        """Handle schema migrations."""
        if not self._conn:
            return
        if old_version < 2:
            try:
                self._conn.execute("ALTER TABLE files ADD COLUMN extension TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
        if old_version < 3:
            try:
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS parsed_ast (
                        path        TEXT PRIMARY KEY,
                        mtime       REAL,
                        size_bytes  INTEGER,
                        data_json   TEXT
                    )
                """)
            except sqlite3.OperationalError:
                pass

    def _get_meta(self, key: str) -> Optional[str]:
        if not self._conn:
            return None
        try:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None
        except sqlite3.OperationalError:
            return None

    def _set_meta(self, key: str, value: str):
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value)
            )
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache _set_meta skipped: {e}")

    # ── File operations ──────────────────────────────────────────────────────

    def is_file_cached(self, path: str, mtime: float, size: int) -> bool:
        """Return True if this file was already analyzed and hasn't changed."""
        if not self._conn:
            return False
        try:
            row = self._conn.execute(
                "SELECT mtime, size_bytes, analysis_done FROM files WHERE path=?", (path,)
            ).fetchone()
            if not row:
                return False
            return (
                row["analysis_done"] == 1
                and abs(row["mtime"] - mtime) < 0.01
                and row["size_bytes"] == size
            )
        except sqlite3.OperationalError:
            return False

    def upsert_file(
        self,
        path: str,
        name: str,
        node_type: str,
        size_bytes: int,
        mtime: float,
        extension: str,
        analysis_done: bool = False,
    ):
        if not self._conn:
            return
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO files
                    (path, name, node_type, size_bytes, mtime, analysis_done, analysis_ts, extension)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path, name, node_type, size_bytes, mtime,
                    1 if analysis_done else 0,
                    time.time() if analysis_done else 0.0,
                    extension,
                ),
            )
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache upsert_file skipped: {e}")

    def mark_file_analyzed(self, path: str):
        if not self._conn:
            return
        try:
            self._conn.execute(
                "UPDATE files SET analysis_done=1, analysis_ts=? WHERE path=?",
                (time.time(), path),
            )
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache mark_file_analyzed skipped: {e}")

    def get_all_files(self) -> List[dict]:
        if not self._conn:
            return []
        try:
            rows = self._conn.execute("SELECT * FROM files").fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def delete_file(self, path: str):
        if not self._conn:
            return
        try:
            norm_path = str(Path(path).resolve())
        except Exception:
            norm_path = path
        try:
            self._conn.execute(
                "DELETE FROM files WHERE path=? OR path=?", (path, norm_path)
            )
            self._conn.execute(
                "DELETE FROM edges WHERE source=? OR target=? OR source=? OR target=?",
                (path, path, norm_path, norm_path)
            )
            self._conn.execute("DELETE FROM parsed_ast WHERE path=? OR path=?", (path, norm_path))
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache delete_file skipped: {e}")

    def get_parsed_ast(self, path: str, mtime: float, size: int) -> Optional[dict]:
        """Return cached AST parse results if file has not changed."""
        if not self._conn:
            return None
        try:
            norm_path = str(Path(path).resolve())
        except Exception:
            norm_path = path

        try:
            row = self._conn.execute(
                "SELECT mtime, size_bytes, data_json FROM parsed_ast WHERE path=?", (norm_path,)
            ).fetchone()
            if not row:
                # Fallback to literal path
                row = self._conn.execute(
                    "SELECT mtime, size_bytes, data_json FROM parsed_ast WHERE path=?", (path,)
                ).fetchone()
            if not row:
                return None
            if abs(row["mtime"] - mtime) < 0.01 and row["size_bytes"] == size:
                try:
                    return json.loads(row["data_json"])
                except Exception:
                    return None
        except sqlite3.OperationalError:
            return None
        return None

    def save_parsed_ast(self, path: str, mtime: float, size: int, data: dict):
        """Cache AST parse results for instant subsequent lookups."""
        if not self._conn:
            return
        try:
            norm_path = str(Path(path).resolve())
        except Exception:
            norm_path = path

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO parsed_ast (path, mtime, size_bytes, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (norm_path, mtime, size, json.dumps(data)),
            )
        except Exception as e:
            logger.debug(f"Failed to cache AST for {path}: {e}")

    # ── Edge operations ──────────────────────────────────────────────────────

    def upsert_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        confidence: str,
        method: str,
        line_number: Optional[int] = None,
        raw_text: Optional[str] = None,
    ):
        if not self._conn:
            return
        try:
            # Check for duplicate
            existing = self._conn.execute(
                """
                SELECT id FROM edges
                WHERE source=? AND target=? AND edge_type=? AND method=?
                """,
                (source, target, edge_type, method),
            ).fetchone()
            if not existing:
                self._conn.execute(
                    """
                    INSERT INTO edges (source, target, edge_type, confidence, method, line_number, raw_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source, target, edge_type, confidence, method, line_number, raw_text),
                )
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache upsert_edge skipped: {e}")

    def get_edges_from(self, source: str) -> List[dict]:
        if not self._conn:
            return []
        try:
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE source=?", (source,)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def get_edges_to(self, target: str) -> List[dict]:
        if not self._conn:
            return []
        try:
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE target=?", (target,)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def get_all_edges(self) -> List[dict]:
        if not self._conn:
            return []
        try:
            rows = self._conn.execute("SELECT * FROM edges").fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def delete_edges_from(self, source: str):
        if not self._conn:
            return
        try:
            self._conn.execute("DELETE FROM edges WHERE source=?", (source,))
        except sqlite3.OperationalError as e:
            logger.debug(f"IndexCache delete_edges_from skipped: {e}")

    # ── Batch operations ─────────────────────────────────────────────────────

    def commit(self):
        if self._conn:
            try:
                self._conn.commit()
            except Exception:
                pass

    def close(self):
        if self._conn:
            try:
                self._conn.commit()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def set_project_root(self, root: str):
        self._set_meta("project_root", root)
        self._set_meta("last_scan", str(time.time()))
        self.commit()

    def get_project_root(self) -> Optional[str]:
        return self._get_meta("project_root")

    def get_stats(self) -> dict:
        if not self._conn:
            return {
                "total_files": 0,
                "analyzed_files": 0,
                "total_edges": 0,
                "last_scan": 0.0,
            }
        try:
            n_files = self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            n_analyzed = self._conn.execute(
                "SELECT COUNT(*) FROM files WHERE analysis_done=1"
            ).fetchone()[0]
            n_edges = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            last_scan = self._get_meta("last_scan")
            return {
                "total_files": n_files,
                "analyzed_files": n_analyzed,
                "total_edges": n_edges,
                "last_scan": float(last_scan) if last_scan else 0.0,
            }
        except sqlite3.OperationalError:
            return {
                "total_files": 0,
                "analyzed_files": 0,
                "total_edges": 0,
                "last_scan": 0.0,
            }
