"""
app/state/scanner.py

Filesystem scanner: walks a project directory and collects file metadata.
Targeted scanning — reads only what's needed per file type.
Deterministic — no AI.
"""
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Callable, Dict, Generator, List, Optional, Set

from app.graph.models import GraphNode, NodeType


# Directories to skip during scanning
SKIP_DIRS: Set[str] = {
    ".git", ".hg", ".svn", ".tox", ".mypy_cache",
    "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    ".eggs", ".idea", ".vscode",
    "__MACOSX", ".DS_Store",
    "$RECYCLE.BIN", "$Recycle.Bin", "System Volume Information",
    "Recovery", "AppData", "Application Data", "Windows",
    "Program Files", "Program Files (x86)", "Local Settings",
    "anaconda3", "miniconda3", ".conda", "conda", "site-packages",
}

# File extensions to include in scanning (add more as needed)
INCLUDE_EXTENSIONS: Set[str] = {
    # Python
    ".py", ".pyx", ".pxd",
    # Config
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env",
    # Data / Models
    ".csv", ".tsv", ".parquet", ".pkl", ".pickle",
    ".pt", ".pth", ".h5", ".hdf5", ".onnx",
    ".npy", ".npz", ".bin", ".weights",
    # Text
    ".txt", ".md", ".rst", ".log",
    # Scripts
    ".sh", ".bat", ".ps1", ".cmd",
    # Web
    ".html", ".htm", ".js", ".ts", ".css",
    # Other
    ".xml", ".sql", ".ipynb",
}

MAX_FILE_SIZE_FOR_CONTENT = 5 * 1024 * 1024  # 5 MB — don't read larger files


class FileScanner:
    """
    Walks a project directory and produces GraphNode objects.
    Uses targeted scanning — never blindly reads all file contents.
    """

    def __init__(
        self,
        root: Path,
        skip_dirs: Optional[Set[str]] = None,
        include_extensions: Optional[Set[str]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        self.root = root.resolve()
        self.skip_dirs = skip_dirs or SKIP_DIRS
        self.include_extensions = include_extensions or INCLUDE_EXTENSIONS
        self.progress_callback = progress_callback

    def scan(self) -> Dict[str, GraphNode]:
        """
        Scan the project root and return a dict of {path_str: GraphNode}.
        """
        nodes: Dict[str, GraphNode] = {}
        start = time.monotonic()

        # Add root folder node
        root_node = GraphNode.from_path(self.root, NodeType.FOLDER)
        nodes[str(self.root)] = root_node

        count = 0
        for filepath in self._walk():
            try:
                node = GraphNode.from_path(filepath)
                nodes[str(filepath)] = node
                count += 1
                if self.progress_callback and count % 50 == 0:
                    self.progress_callback(f"Scanned {count} files...")
            except Exception:
                pass

        elapsed = time.monotonic() - start
        if self.progress_callback:
            self.progress_callback(f"Scan complete: {len(nodes)} items in {elapsed*1000:.0f}ms")

        return nodes

    def _walk(self) -> Generator[Path, None, None]:
        """Walk directory tree, yielding relevant file paths."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter skip dirs in-place (modifies dirnames to prevent descending)
            dirnames[:] = [
                d for d in dirnames
                if d not in self.skip_dirs
                and not d.endswith(".egg-info")
                and not d.startswith(".")
                and not d.startswith("$")
            ]
            dirnames.sort()

            # Yield valid subdirectories so project folders (e.g. dataset, models) are indexed
            for dirname in dirnames:
                yield Path(dirpath) / dirname

            for filename in sorted(filenames):
                filepath = Path(dirpath) / filename
                ext = filepath.suffix.lower()

                if ext in self.include_extensions:
                    yield filepath
                elif not filepath.suffix:
                    # Files without extension — include if small enough to be a script
                    try:
                        if filepath.stat().st_size < 100 * 1024:
                            yield filepath
                    except OSError:
                        pass

    def get_all_filenames(self, nodes: Dict[str, GraphNode]) -> Set[str]:
        """Return the set of all bare filenames (without directory) from scanned nodes."""
        return {node.name for node in nodes.values()}

    def get_python_files(self, nodes: Dict[str, GraphNode]) -> List[Path]:
        """Return all Python file paths from scanned nodes."""
        return [
            Path(node.path)
            for node in nodes.values()
            if node.extension == ".py" and node.node_type != NodeType.FOLDER
        ]

    def get_config_files(self, nodes: Dict[str, GraphNode]) -> List[Path]:
        """Return all config file paths from scanned nodes."""
        config_exts = {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env", ".txt"}
        return [
            Path(node.path)
            for node in nodes.values()
            if node.extension in config_exts and node.node_type != NodeType.FOLDER
        ]
