"""
app/parsing/python_parser.py

Extracts imports, file references, and dependencies from Python files
using the built-in `ast` module. Fully deterministic — no AI.
"""
from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple


class PythonParser:
    """
    Statically analyzes Python files to extract:
    - imports (import X, from X import Y)
    - file path references (open("file"), load("file"), pickle.load, etc.)
    - string literals that look like file paths
    """

    # Patterns that suggest file loading
    LOAD_FUNCTIONS = {
        "open", "load", "loads", "read", "pickle.load",
        "joblib.load", "torch.load", "np.load", "pd.read_csv",
        "pd.read_json", "pd.read_excel", "pd.read_parquet",
        "json.load", "yaml.load", "yaml.safe_load", "toml.load",
        "cv2.imread", "PIL.Image.open", "Image.open",
    }

    # File extensions that suggest a file reference string
    FILE_EXTENSIONS = {
        ".pkl", ".pickle", ".pt", ".pth", ".h5", ".hdf5",
        ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml",
        ".txt", ".log", ".cfg", ".ini", ".env",
        ".onnx", ".pb", ".tflite", ".bin", ".weights",
        ".png", ".jpg", ".jpeg", ".mp4", ".wav",
        ".npy", ".npz", ".parquet",
    }

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root

    def parse_file(self, filepath: Path) -> dict:
        """
        Parse a Python file and return all discovered references.

        Returns:
            {
                "imports": [...],
                "file_references": [...],
                "string_paths": [...],
            }
        """
        result = {
            "imports": [],
            "file_references": [],
            "string_paths": [],
            "errors": [],
        }

        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result["errors"].append(str(e))
            return result

        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError as e:
            result["errors"].append(f"SyntaxError: {e}")
            # Fall back to regex-based extraction
            result["string_paths"] = self._regex_extract_paths(source, filepath)
            result["file_references"] = self._regex_extract_loads(source, filepath)
            return result

        result["imports"] = self._extract_imports(tree, filepath)
        result["file_references"] = self._extract_file_loads(tree, source, filepath)
        result["string_paths"] = self._extract_string_paths(tree, filepath)

        return result

    def _extract_imports(self, tree: ast.AST, filepath: Path) -> List[dict]:
        """Extract all import statements."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "type": "import",
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                        "type": "from_import",
                    })
        return imports

    def _extract_file_loads(self, tree: ast.AST, source: str, filepath: Path) -> List[dict]:
        """
        Find calls like open("model.pkl"), pickle.load("..."), pd.read_csv("dataset.csv").
        """
        references = []
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func_name = self._get_call_name(node)
            if not func_name:
                continue

            # Check if any known loading function is called
            is_load_call = any(
                func_name == lf or func_name.endswith("." + lf.split(".")[-1])
                for lf in self.LOAD_FUNCTIONS
            )
            if not is_load_call:
                continue

            # Try to extract the first string argument
            for arg in node.args:
                val = arg.value if hasattr(arg, "value") else getattr(arg, "s", None)
                if isinstance(arg, ast.Constant) and isinstance(val, str):
                    path_str = val
                    if self._looks_like_file_path(path_str):
                        raw_line = source_lines[node.lineno - 1].strip() if node.lineno <= len(source_lines) else ""
                        references.append({
                            "function": func_name,
                            "path": path_str,
                            "line": node.lineno,
                            "raw": raw_line,
                        })

        return references

    def _extract_string_paths(self, tree: ast.AST, filepath: Path) -> List[dict]:
        """Extract string literals that look like file paths."""
        paths = []
        for node in ast.walk(tree):
            val = node.value if hasattr(node, "value") else getattr(node, "s", None)
            if isinstance(node, ast.Constant) and isinstance(val, str):
                s = val
                if self._looks_like_file_path(s) and len(s) > 3:
                    paths.append({
                        "value": s,
                        "line": getattr(node, "lineno", None),
                    })
        return paths

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Get the full dotted name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            n = node.func
            while isinstance(n, ast.Attribute):
                parts.append(n.attr)
                n = n.value
            if isinstance(n, ast.Name):
                parts.append(n.id)
            return ".".join(reversed(parts))
        return None

    def _looks_like_file_path(self, s: str) -> bool:
        """Heuristic: does this string look like a file path?"""
        if not s or len(s) > 256:
            return False
        p = Path(s)
        # Has a known file extension
        if p.suffix.lower() in self.FILE_EXTENSIONS:
            return True
        # Contains path separators and looks like a path
        if ("/" in s or "\\" in s) and not s.startswith("http"):
            return True
        return False

    def _regex_extract_paths(self, source: str, filepath: Path) -> List[dict]:
        """Fallback: regex-based path extraction when AST fails."""
        results = []
        # Match quoted strings that look like file paths
        pattern = r'["\']([^"\']*\.[a-z]{2,5})["\']'
        for m in re.finditer(pattern, source, re.IGNORECASE):
            s = m.group(1)
            if self._looks_like_file_path(s):
                results.append({"value": s, "line": source[:m.start()].count("\n") + 1})
        return results

    def _regex_extract_loads(self, source: str, filepath: Path) -> List[dict]:
        """Fallback: regex-based load function detection."""
        results = []
        pattern = r'(?:open|load|read|pd\.read_\w+)\s*\(\s*["\']([^"\']+)["\']'
        for m in re.finditer(pattern, source, re.IGNORECASE):
            s = m.group(1)
            if self._looks_like_file_path(s):
                results.append({
                    "function": "unknown",
                    "path": s,
                    "line": source[:m.start()].count("\n") + 1,
                    "raw": m.group(0),
                })
        return results

    def resolve_reference(self, ref_path: str, from_file: Path, project_root: Optional[Path] = None) -> Optional[Path]:
        """
        Try to resolve a referenced path relative to the calling file
        and the project root.
        """
        root = project_root or self.project_root or from_file.parent
        candidates = [
            from_file.parent / ref_path,
            root / ref_path,
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return None
