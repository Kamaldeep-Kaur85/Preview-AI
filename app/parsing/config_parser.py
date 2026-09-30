"""
app/parsing/config_parser.py

Parse configuration files (JSON, YAML, TOML, requirements.txt, .env)
to extract file references and dependency declarations.
Deterministic — no AI.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConfigParser:
    """
    Parses configuration files to find:
    - file path references
    - package dependencies (requirements.txt, pyproject.toml)
    - model references
    """

    FILE_LIKE_PATTERN = re.compile(
        r'["\']?([A-Za-z0-9_\-./\\]+\.[a-z]{2,6})["\']?',
        re.IGNORECASE
    )

    def parse_file(self, filepath: Path) -> dict:
        """Parse a config file and return extracted references."""
        ext = filepath.suffix.lower()
        name = filepath.name.lower()

        if name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
            return self._parse_requirements(filepath)
        elif ext == ".json":
            return self._parse_json(filepath)
        elif ext in (".yaml", ".yml"):
            return self._parse_yaml(filepath)
        elif ext in (".toml",):
            return self._parse_toml(filepath)
        elif ext in (".env", ".cfg", ".ini"):
            return self._parse_env_style(filepath)
        else:
            return self._generic_parse(filepath)

    def _parse_requirements(self, filepath: Path) -> dict:
        """Parse requirements.txt — extract package names."""
        packages = []
        file_refs = []
        try:
            for line in filepath.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("-r ") or line.startswith("--requirement"):
                    # Reference to another requirements file
                    ref = line.split(None, 1)[1].strip()
                    file_refs.append({"path": ref, "type": "include"})
                    continue
                # Strip version specifiers
                pkg = re.split(r"[>=<!~\[;]", line)[0].strip()
                if pkg:
                    packages.append({"name": pkg, "raw": line})
        except Exception as e:
            return {"error": str(e), "packages": [], "file_refs": []}

        return {
            "type": "requirements",
            "packages": packages,
            "file_refs": file_refs,
        }

    def _parse_json(self, filepath: Path) -> dict:
        """Parse JSON config and extract file-path-like values."""
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            data = json.loads(text)
            file_refs = self._extract_paths_from_obj(data)
            return {"type": "json", "file_refs": file_refs, "keys": list(data.keys()) if isinstance(data, dict) else []}
        except json.JSONDecodeError as e:
            # Fall back to regex scan
            file_refs = self._regex_scan(filepath)
            return {"type": "json_invalid", "file_refs": file_refs, "error": str(e)}
        except Exception as e:
            return {"type": "json", "file_refs": [], "error": str(e)}

    def _parse_yaml(self, filepath: Path) -> dict:
        """Parse YAML config — try with PyYAML if available, else regex."""
        try:
            import yaml  # type: ignore
            text = filepath.read_text(encoding="utf-8", errors="replace")
            data = yaml.safe_load(text)
            file_refs = self._extract_paths_from_obj(data) if data else []
            return {"type": "yaml", "file_refs": file_refs}
        except ImportError:
            # PyYAML not available — use regex
            file_refs = self._regex_scan(filepath)
            return {"type": "yaml_regex", "file_refs": file_refs}
        except Exception as e:
            file_refs = self._regex_scan(filepath)
            return {"type": "yaml", "file_refs": file_refs, "error": str(e)}

    def _parse_toml(self, filepath: Path) -> dict:
        """Parse TOML — use tomllib (Python 3.11+) or tomli."""
        try:
            try:
                import tomllib  # Python 3.11+
                with open(filepath, "rb") as f:
                    data = tomllib.load(f)
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore
                    with open(filepath, "rb") as f:
                        data = tomllib.load(f)
                except ImportError:
                    return {"type": "toml_regex", "file_refs": self._regex_scan(filepath)}

            # Extract dependencies from pyproject.toml
            packages = []
            if "project" in data and "dependencies" in data["project"]:
                for dep in data["project"]["dependencies"]:
                    pkg = re.split(r"[>=<!~\[;]", dep)[0].strip()
                    packages.append({"name": pkg, "raw": dep})

            file_refs = self._extract_paths_from_obj(data)
            return {"type": "toml", "packages": packages, "file_refs": file_refs}
        except Exception as e:
            return {"type": "toml", "file_refs": self._regex_scan(filepath), "error": str(e)}

    def _parse_env_style(self, filepath: Path) -> dict:
        """Parse .env / .cfg / .ini style files for path references."""
        file_refs = self._regex_scan(filepath)
        return {"type": "env", "file_refs": file_refs}

    def _generic_parse(self, filepath: Path) -> dict:
        """Generic text-based scan for file references."""
        file_refs = self._regex_scan(filepath)
        return {"type": "generic", "file_refs": file_refs}

    def _extract_paths_from_obj(self, obj: Any, depth: int = 0) -> List[dict]:
        """Recursively extract file-path-like strings from a parsed object."""
        if depth > 10:
            return []
        results = []
        if isinstance(obj, str):
            if self._looks_like_path(obj):
                results.append({"value": obj, "source": "config_value"})
        elif isinstance(obj, dict):
            for k, v in obj.items():
                results.extend(self._extract_paths_from_obj(v, depth + 1))
                if isinstance(k, str) and self._looks_like_path(k):
                    results.append({"value": k, "source": "config_key"})
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                results.extend(self._extract_paths_from_obj(item, depth + 1))
        return results

    def _regex_scan(self, filepath: Path) -> List[dict]:
        """Regex-based file path detection in any text file."""
        results = []
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            for m in self.FILE_LIKE_PATTERN.finditer(text):
                s = m.group(1)
                if self._looks_like_path(s) and len(s) > 3:
                    results.append({
                        "value": s,
                        "line": text[:m.start()].count("\n") + 1,
                        "source": "regex",
                    })
        except Exception:
            pass
        return results

    def _looks_like_path(self, s: str) -> bool:
        """Heuristic: is this string a file path?"""
        if not s or len(s) > 256 or len(s) < 3:
            return False
        # Must have extension or path separator
        ext = Path(s).suffix.lower()
        has_known_ext = ext in {
            ".py", ".pkl", ".csv", ".json", ".yaml", ".yml",
            ".toml", ".cfg", ".ini", ".env", ".txt", ".log",
            ".onnx", ".pt", ".h5", ".bin", ".npy", ".npz",
            ".png", ".jpg", ".mp4", ".wav",
        }
        has_separator = ("/" in s or "\\" in s) and not s.startswith("http")
        return has_known_ext or has_separator
