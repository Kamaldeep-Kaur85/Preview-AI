"""
app/ai/global_search.py

Global File Explorer search engine with intelligent layered discovery:
LEVEL 1 — Current folder / project (fully indexed / immediate)
LEVEL 2 — Previously indexed locations (searches IndexCache SQLite)
LEVEL 3 — File Explorer discovery (shallow, bounded walk of accessible drives/common directories)
LEVEL 4 — Explicit user request (searches user-specified directory directly)

Translates natural-language search requests into File Explorer search operations.
Never invents paths. Always checks real filesystem existence.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# System and hidden directories to strictly skip during discovery
SKIPPED_DIR_NAMES: Set[str] = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    ".git",
    ".venv",
    "venv",
    "conda",
    "anaconda3",
    "miniconda3",
    ".conda",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".cache",
}


from enum import Enum


class SearchScope(str, Enum):
    PROJECT = "PROJECT"
    CURRENT_FOLDER = "CURRENT_FOLDER"
    SELECTED_FOLDERS = "SELECTED_FOLDERS"
    APPROVED_LOCATIONS = "APPROVED_LOCATIONS"


@dataclass
class SearchResultItem:
    """Represents a verified file or folder found during search."""
    path: str
    name: str
    size_bytes: int
    mtime: float
    extension: str
    is_dir: bool = False
    layer: int = 1  # 1 = Current folder, 2 = Indexed cache, 3 = Explorer discovery, 4 = Explicit location
    snippet: Optional[str] = None

    @property
    def formatted_size(self) -> str:
        if self.is_dir:
            return "Folder"
        size = self.size_bytes
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.1f} GB"

    @property
    def formatted_mtime(self) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))
        except Exception:
            return ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "extension": self.extension,
            "is_dir": self.is_dir,
            "layer": self.layer,
            "snippet": self.snippet,
        }


class GlobalSearchEngine:
    """
    Intelligent layered search engine across the accessible File Explorer scope.
    Supports explicit search scopes:
    - CURRENT FOLDER
    - PROJECT
    - SELECTED FOLDERS
    - USER-APPROVED LOCATIONS
    """

    def __init__(
        self,
        current_nav_path: Optional[str] = None,
        cache=None,
        known_locations: Optional[List[str]] = None,
        scope: SearchScope = SearchScope.PROJECT,
    ):
        self.current_nav_path: Optional[Path] = (
            Path(current_nav_path).resolve() if current_nav_path else None
        )
        self.cache = cache
        self.known_locations: Set[str] = set()
        self.approved_locations: Set[str] = set()
        self.selected_folders: List[str] = []
        self.scope: SearchScope = scope if isinstance(scope, SearchScope) else SearchScope(str(scope).upper())

        if self.current_nav_path:
            self.known_locations.add(str(self.current_nav_path))
            self.approved_locations.add(str(self.current_nav_path))
        if known_locations:
            for loc in known_locations:
                if loc and Path(loc).exists():
                    resolved = str(Path(loc).resolve())
                    self.known_locations.add(resolved)
                    self.approved_locations.add(resolved)

    def set_scope(self, scope: SearchScope | str):
        """Set the active search scope."""
        if isinstance(scope, str):
            s = scope.upper()
            if "FOLDER" in s and "CURRENT" in s:
                self.scope = SearchScope.CURRENT_FOLDER
            elif "SELECT" in s:
                self.scope = SearchScope.SELECTED_FOLDERS
            elif "APPROV" in s:
                self.scope = SearchScope.APPROVED_LOCATIONS
            else:
                self.scope = SearchScope.PROJECT
        else:
            self.scope = scope

    def add_approved_location(self, path: str) -> bool:
        """Allow the user to add and approve another location to search index."""
        try:
            p = Path(path).resolve()
            if p.exists() and p.is_dir():
                self.approved_locations.add(str(p))
                self.known_locations.add(str(p))
                return True
        except Exception:
            pass
        return False

    def set_selected_folders(self, folders: List[str]):
        """Set explicitly selected folders for search."""
        self.selected_folders = [str(Path(f).resolve()) for f in folders if Path(f).exists()]

    def get_scope_display(self) -> str:
        """Return clear visual indicator of the active search scope."""
        is_proj = "●" if self.scope == SearchScope.PROJECT else "○"
        is_folder = "●" if self.scope == SearchScope.CURRENT_FOLDER else "○"
        is_sel = "●" if self.scope in (SearchScope.SELECTED_FOLDERS, SearchScope.APPROVED_LOCATIONS) else "○"
        return (
            f"Search scope:\n"
            f"{is_proj} Current Project\n"
            f"{is_folder} This Folder\n"
            f"{is_sel} Selected Locations"
        )

    def set_navigation_path(self, path: str):
        """Update current navigation context."""
        try:
            p = Path(path).resolve()
            if p.exists():
                self.current_nav_path = p
                self.known_locations.add(str(p))
                self.approved_locations.add(str(p))
        except Exception:
            pass

    def add_known_location(self, path: str):
        """Record a previously opened or indexed location."""
        try:
            p = Path(path).resolve()
            if p.exists():
                self.known_locations.add(str(p))
                self.approved_locations.add(str(p))
        except Exception:
            pass

    # ── Accessible discovery roots ──────────────────────────────────────────

    def get_discovery_roots(self) -> List[Path]:
        """
        Get accessible directories for Level 3 search without deep-scanning full system drives.
        Includes:
        - Parent / sibling folders of current navigation path
        - User standard directories (Documents, Downloads, Desktop)
        - Drive root user folders
        - Previously known locations
        """
        roots: List[Path] = []
        seen: Set[str] = set()

        def is_drive_root(p: Path) -> bool:
            try:
                rp = p.resolve()
                return rp.parent == rp or len(rp.parts) <= 1 or str(rp).rstrip("\\/").endswith(":")
            except Exception:
                return True

        def add_root(p: Path):
            try:
                rp = p.resolve()
                if rp.exists() and rp.is_dir() and str(rp).lower() not in seen:
                    # Never add root of any drive directly (e.g. C:\ or D:\)
                    if is_drive_root(rp):
                        return
                    if rp.name.lower() in SKIPPED_DIR_NAMES:
                        return
                    seen.add(str(rp).lower())
                    roots.append(rp)
            except Exception:
                pass

        # 1. Current navigation path & sibling directories
        if self.current_nav_path and self.current_nav_path.exists():
            add_root(self.current_nav_path)
            parent = self.current_nav_path.parent
            if parent and parent != self.current_nav_path:
                if not is_drive_root(parent):
                    add_root(parent)
                # Add up to 10 immediate siblings
                try:
                    siblings = [
                        s for s in parent.iterdir()
                        if s.is_dir() and not s.name.startswith((".", "$")) and s.name.lower() not in SKIPPED_DIR_NAMES
                    ][:10]
                    for s in siblings:
                        add_root(s)
                except Exception:
                    pass

        # 2. Known locations (registered via UI, past history, or tests)
        for loc in list(self.known_locations):
            add_root(Path(loc))

        # 3. User standard profile folders
        try:
            home = Path.home()
            for sub in ("Documents", "Downloads", "Desktop", "Projects"):
                cand = home / sub
                if cand.exists():
                    add_root(cand)
        except Exception:
            pass

        # 4. Standard common folders on D:\ if exists (e.g. D:\Documents, D:\Projects, D:\datasets)
        d_drive = Path("D:/")
        if d_drive.exists():
            for sub in ("Documents", "Projects", "datasets", "data", "Downloads", "Desktop"):
                cand = d_drive / sub
                if cand.exists():
                    add_root(cand)

        return roots

    # ── Layered search core ─────────────────────────────────────────────────

    def search(
        self,
        query: str,
        explicit_location: Optional[str] = None,
        max_results: int = 50,
        extensions: Optional[List[str]] = None,
        only_recent: bool = False,
        scope: Optional[SearchScope | str] = None,
    ) -> List[SearchResultItem]:
        """
        Execute scoped search across user-approved and indexed locations.
        """
        clean_query = query.strip()
        results: List[SearchResultItem] = []
        seen_paths: Set[str] = set()

        active_scope = self.scope if scope is None else (
            scope if isinstance(scope, SearchScope) else SearchScope(str(scope).upper())
        )

        def add_item(item: SearchResultItem):
            norm = os.path.normcase(os.path.abspath(item.path))
            if norm not in seen_paths:
                seen_paths.add(norm)
                results.append(item)

        # ── LEVEL 4: Explicit user location / Selected Folders ─────────────
        if explicit_location:
            loc_path = Path(explicit_location).resolve()
            if loc_path.exists() and loc_path.is_dir():
                items = self._search_directory(
                    loc_path,
                    clean_query,
                    max_depth=3,
                    layer=4,
                    extensions=extensions,
                    max_items=max_results,
                )
                for item in items:
                    add_item(item)
                if only_recent:
                    results.sort(key=lambda x: x.mtime, reverse=True)
                return results[:max_results]

        if active_scope == SearchScope.CURRENT_FOLDER:
            # Strictly search current folder only
            if self.current_nav_path and self.current_nav_path.exists():
                l1_items = self._search_directory(
                    self.current_nav_path,
                    clean_query,
                    max_depth=1,
                    layer=1,
                    extensions=extensions,
                    max_items=max_results,
                )
                for item in l1_items:
                    add_item(item)
            return results[:max_results]

        if active_scope == SearchScope.SELECTED_FOLDERS:
            # Search user-selected folders
            for sel_f in self.selected_folders:
                p = Path(sel_f)
                if p.exists() and p.is_dir():
                    for item in self._search_directory(p, clean_query, max_depth=3, layer=1, extensions=extensions, max_items=max_results):
                        add_item(item)
            return results[:max_results]

        if active_scope == SearchScope.APPROVED_LOCATIONS:
            # Search user-approved locations
            for app_loc in self.approved_locations:
                p = Path(app_loc)
                if p.exists() and p.is_dir():
                    for item in self._search_directory(p, clean_query, max_depth=3, layer=1, extensions=extensions, max_items=max_results):
                        add_item(item)
            return results[:max_results]

        # ── LEVEL 1: Current folder / project ──────────────────────────────
        if self.current_nav_path and self.current_nav_path.exists():
            l1_items = self._search_directory(
                self.current_nav_path,
                clean_query,
                max_depth=3,
                layer=1,
                extensions=extensions,
                max_items=max_results,
            )
            for item in l1_items:
                add_item(item)

        # ── LEVEL 2: Previously indexed locations (IndexCache SQLite) ──────
        if len(results) < max_results and self.cache:
            l2_items = self._search_cache(clean_query, extensions=extensions)
            for item in l2_items:
                add_item(item)

        # ── LEVEL 3: File Explorer discovery ───────────────────────────────
        if len(results) < max_results and active_scope != SearchScope.CURRENT_FOLDER:
            discovery_roots = self.get_discovery_roots()
            t0 = time.monotonic()
            for root in discovery_roots:
                if self.current_nav_path and root.resolve() == self.current_nav_path.resolve():
                    continue
                if time.monotonic() - t0 > 1.5:
                    break
                rem = max_results - len(results)
                if rem <= 0:
                    break
                l3_items = self._search_directory(
                    root,
                    clean_query,
                    max_depth=2,
                    layer=3,
                    extensions=extensions,
                    max_items=rem,
                )
                for item in l3_items:
                    add_item(item)

        if only_recent:
            results.sort(key=lambda x: x.mtime, reverse=True)
        elif clean_query and clean_query != "*":
            q_stem = Path(clean_query).stem.lower()
            def match_score(item: SearchResultItem):
                stem = Path(item.name).stem.lower()
                if stem == q_stem:
                    return (0, item.layer)
                if stem.startswith(q_stem):
                    return (1, item.layer)
                return (2, item.layer)
            results.sort(key=match_score)

        return results[:max_results]

    def _search_directory(
        self,
        directory: Path,
        query: str,
        max_depth: int = 3,
        layer: int = 1,
        extensions: Optional[List[str]] = None,
        max_items: int = 50,
    ) -> List[SearchResultItem]:
        """
        Shallow, bounded filesystem scan of a directory.
        """
        items: List[SearchResultItem] = []
        q_lower = query.lower()
        # Clean regex / pattern from query
        pattern = self._build_match_pattern(q_lower)
        exts_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None

        base_depth = len(directory.resolve().parts)

        try:
            for root, dirs, files in os.walk(directory):
                # Filter out ignored directories
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith((".", "$")) and d.lower() not in SKIPPED_DIR_NAMES
                ]

                cur_depth = len(Path(root).parts) - base_depth
                if cur_depth >= max_depth:
                    dirs.clear()

                root_path = Path(root)

                # Check subfolder matches
                for d in dirs:
                    d_lower = d.lower()
                    if pattern and pattern.search(d_lower):
                        full_dp = root_path / d
                        try:
                            st = full_dp.stat()
                            items.append(SearchResultItem(
                                path=str(full_dp),
                                name=d,
                                size_bytes=0,
                                mtime=st.st_mtime,
                                extension="",
                                is_dir=True,
                                layer=layer,
                            ))
                            if len(items) >= max_items:
                                return items
                        except (OSError, PermissionError):
                            pass

                # Check files
                for f in files:
                    if f.startswith((".", "$")):
                        continue
                    f_lower = f.lower()
                    f_ext = Path(f).suffix.lower()

                    if exts_set and f_ext not in exts_set:
                        continue

                    # Match logic
                    matched = False
                    if not q_lower or q_lower == "*":
                        matched = True
                    elif pattern and pattern.search(f_lower):
                        matched = True

                    if matched:
                        full_fp = root_path / f
                        try:
                            st = full_fp.stat()
                            items.append(SearchResultItem(
                                path=str(full_fp),
                                name=f,
                                size_bytes=st.st_size,
                                mtime=st.st_mtime,
                                extension=f_ext,
                                is_dir=False,
                                layer=layer,
                            ))
                            if len(items) >= max_items:
                                return items
                        except (OSError, PermissionError):
                            pass

        except (OSError, PermissionError):
            pass

        return items

    def _search_cache(
        self,
        query: str,
        extensions: Optional[List[str]] = None,
    ) -> List[SearchResultItem]:
        """
        Search SQLite IndexCache for matching files previously indexed.
        """
        if not self.cache or not getattr(self.cache, "_conn", None):
            return []

        items: List[SearchResultItem] = []
        exts_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None

        try:
            cur = self.cache._conn.cursor()
            sql = "SELECT path, name, node_type, size_bytes, mtime, extension FROM files"
            params = []
            if query and query != "*":
                sql += " WHERE name LIKE ?"
                params.append(f"%{query}%")
            sql += " ORDER BY mtime DESC LIMIT 100"
            rows = cur.execute(sql, params).fetchall()

            for r in rows:
                p_str = r["path"]
                p = Path(p_str)
                # Verify actual filesystem existence
                if not p.exists():
                    continue

                ext = r["extension"] or p.suffix.lower()
                if exts_set and ext.lower() not in exts_set:
                    continue

                items.append(SearchResultItem(
                    path=str(p.resolve()),
                    name=r["name"] or p.name,
                    size_bytes=r["size_bytes"] or 0,
                    mtime=r["mtime"] or 0.0,
                    extension=ext,
                    is_dir=(r["node_type"] == "FOLDER"),
                    layer=2,
                ))
        except Exception:
            pass

        return items

    def _build_match_pattern(self, query: str) -> Optional[re.Pattern]:
        """Compile regex pattern for query matching."""
        if not query or query == "*":
            return None
        # Escape characters, replace * with .*
        escaped = re.escape(query).replace(r"\*", ".*")
        try:
            return re.compile(escaped, re.IGNORECASE)
        except re.error:
            return None

    # ── Specialized query operations ────────────────────────────────────────

    def inspect_directory(self, dir_path: str) -> List[SearchResultItem]:
        """Inspect contents of a specific directory (e.g. 'What is inside D:\\Projects?')."""
        target = Path(dir_path).resolve()
        if not target.exists() or not target.is_dir():
            return []
        items: List[SearchResultItem] = []
        try:
            for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if entry.name.startswith((".", "$")):
                    continue
                try:
                    st = entry.stat()
                    items.append(SearchResultItem(
                        path=str(entry),
                        name=entry.name,
                        size_bytes=st.st_size if entry.is_file() else 0,
                        mtime=st.st_mtime,
                        extension=entry.suffix.lower() if entry.is_file() else "",
                        is_dir=entry.is_dir(),
                        layer=4,
                    ))
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
        return items

    def find_folders_containing(self, keyword: str, location: Optional[str] = None) -> List[SearchResultItem]:
        """Find folders containing files matching a keyword (e.g. 'Find folders containing datasets')."""
        roots = [Path(location).resolve()] if location else self.get_discovery_roots()
        folder_matches: Dict[str, SearchResultItem] = {}
        kw_lower = keyword.lower()
        t0 = time.monotonic()

        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            if time.monotonic() - t0 > 2.0:
                break
            base_depth = len(root.parts)
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d.lower() not in SKIPPED_DIR_NAMES]
                cur_depth = len(Path(r).parts) - base_depth
                if cur_depth >= 3:
                    dirs.clear()
                if time.monotonic() - t0 > 2.0:
                    break
                cur_path = Path(r)
                # Check if current folder name matches keyword
                if kw_lower in cur_path.name.lower():
                    try:
                        folder_matches[str(cur_path)] = SearchResultItem(
                            path=str(cur_path),
                            name=cur_path.name,
                            size_bytes=0,
                            mtime=cur_path.stat().st_mtime,
                            extension="",
                            is_dir=True,
                            layer=3,
                            snippet="Directory name matches keyword",
                        )
                    except OSError:
                        pass
                # Check if files inside match keyword or common dataset extensions
                for f in files:
                    if kw_lower in f.lower() or (kw_lower == "dataset" and f.lower().endswith((".csv", ".tsv", ".parquet", ".json", ".h5"))):
                        try:
                            if str(cur_path) not in folder_matches:
                                folder_matches[str(cur_path)] = SearchResultItem(
                                    path=str(cur_path),
                                    name=cur_path.name,
                                    size_bytes=0,
                                    mtime=cur_path.stat().st_mtime,
                                    extension="",
                                    is_dir=True,
                                    layer=3,
                                    snippet=f"Contains '{f}'",
                                )
                        except OSError:
                            pass
        return list(folder_matches.values())

    def find_duplicate_files(self, location: Optional[str] = None) -> List[Tuple[SearchResultItem, SearchResultItem]]:
        """Find duplicate-looking files (matching name/size across accessible folders)."""
        roots = [Path(location).resolve()] if location else self.get_discovery_roots()
        files_by_key: Dict[Tuple[str, int], SearchResultItem] = {}
        duplicates: List[Tuple[SearchResultItem, SearchResultItem]] = []
        t0 = time.monotonic()
        total_scanned = 0

        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            if time.monotonic() - t0 > 2.0 or total_scanned >= 500:
                break
            base_depth = len(root.parts)
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith((".", "$")) and d.lower() not in SKIPPED_DIR_NAMES]
                cur_depth = len(Path(r).parts) - base_depth
                if cur_depth >= 3:
                    dirs.clear()
                if time.monotonic() - t0 > 2.0 or total_scanned >= 500:
                    break
                for f in files:
                    if f.startswith((".", "$")):
                        continue
                    fp = Path(r) / f
                    total_scanned += 1
                    try:
                        st = fp.stat()
                        if st.st_size > 0:  # Skip empty files
                            key = (f.lower(), st.st_size)
                            item = SearchResultItem(
                                path=str(fp),
                                name=f,
                                size_bytes=st.st_size,
                                mtime=st.st_mtime,
                                extension=fp.suffix.lower(),
                                is_dir=False,
                            )
                            if key in files_by_key:
                                existing = files_by_key[key]
                                if existing.path != item.path:
                                    duplicates.append((existing, item))
                            else:
                                files_by_key[key] = item
                    except OSError:
                        pass
        return duplicates

    # ── Formatting for AI response ──────────────────────────────────────────

    def format_search_results(
        self,
        query: str,
        results: List[SearchResultItem],
        location_desc: Optional[str] = None,
    ) -> str:
        """Format search results into clean markdown for presentation in the AI chat."""
        if not results:
            loc_str = f" in `{location_desc}`" if location_desc else ""
            return f"No matching files or folders found for **{query}**{loc_str}."

        count = len(results)
        loc_str = f" in `{location_desc}`" if location_desc else ""
        header = f"Found **{count} matching file{'s' if count != 1 else ''}**{loc_str}:\n"

        lines = [header]
        for i, item in enumerate(results, 1):
            icon = "📁" if item.is_dir else "📄"
            snip = f" — *{item.snippet}*" if item.snippet else ""
            lines.append(
                f"{i}. {icon} **{item.name}**\n"
                f"   Path: `{item.path}`\n"
                f"   Size: {item.formatted_size}  •  Modified: {item.formatted_mtime}{snip}"
            )
        return "\n".join(lines)
