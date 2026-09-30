"""
app/parsing/reference_detector.py

Generic text-based reference detection: find filenames, paths, and patterns
that appear in any file type. Used as supplementary evidence.
Deterministic — no AI.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Set


class ReferenceDetector:
    """
    Scans any text file for references to specific filenames or path patterns.
    Used to find cross-references not detected by language-specific parsers.
    """

    def __init__(self, known_filenames: Set[str] = None):
        """
        Args:
            known_filenames: Set of filenames that exist in the project.
                            Any mention of these names is tracked.
        """
        self.known_filenames = known_filenames or set()

    def find_references_to(self, target_name: str, in_file: Path) -> List[dict]:
        """
        Find all mentions of `target_name` (basename) in `in_file`.
        Returns list of {line_number, raw_text, context} dicts.
        """
        results = []
        try:
            text = in_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return results

        # Escape the target for regex
        escaped = re.escape(target_name)
        # Match the name when it appears as a standalone reference
        pattern = re.compile(
            r'(?<![A-Za-z0-9_\-])' + escaped + r'(?![A-Za-z0-9_\-])',
            re.IGNORECASE
        )

        lines = text.splitlines()
        for line_num, line in enumerate(lines, start=1):
            if pattern.search(line):
                results.append({
                    "line_number": line_num,
                    "raw_text": line.strip(),
                    "in_file": str(in_file),
                    "target": target_name,
                })

        return results

    def scan_file_for_known_names(self, filepath: Path) -> List[dict]:
        """
        Scan a file for mentions of any known project filename.
        Returns list of {target, line_number, raw_text} dicts.
        """
        results = []
        if not self.known_filenames:
            return results

        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return results

        lines = text.splitlines()
        for name in self.known_filenames:
            escaped = re.escape(name)
            pattern = re.compile(
                r'(?<![A-Za-z0-9_\-/\\])' + escaped + r'(?![A-Za-z0-9_\-])',
                re.IGNORECASE
            )
            for line_num, line in enumerate(lines, start=1):
                if pattern.search(line):
                    results.append({
                        "target": name,
                        "line_number": line_num,
                        "raw_text": line.strip(),
                        "in_file": str(filepath),
                    })

        return results

    def find_env_variable_references(self, filepath: Path) -> List[dict]:
        """Find environment variable references like ${MY_VAR} or $MY_VAR."""
        results = []
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            pattern = re.compile(r'\$\{?([A-Z_][A-Z0-9_]*)\}?')
            for m in pattern.finditer(text):
                results.append({
                    "variable": m.group(1),
                    "line": text[:m.start()].count("\n") + 1,
                    "raw": m.group(0),
                })
        except Exception:
            pass
        return results
