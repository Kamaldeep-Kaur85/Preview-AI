"""
app/state/project_detector.py

Detects project type (Python, ML, Node.js, etc.) by examining
files and directory structure. Deterministic — no AI.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Set


class ProjectInfo:
    """Information about a detected project."""

    def __init__(
        self,
        root: Path,
        project_type: str = "unknown",
        language: str = "unknown",
        has_requirements: bool = False,
        has_pyproject: bool = False,
        has_setup_py: bool = False,
        has_package_json: bool = False,
        is_ml_project: bool = False,
        entry_points: List[str] = None,
    ):
        self.root = root
        self.project_type = project_type
        self.language = language
        self.has_requirements = has_requirements
        self.has_pyproject = has_pyproject
        self.has_setup_py = has_setup_py
        self.has_package_json = has_package_json
        self.is_ml_project = is_ml_project
        self.entry_points = entry_points or []

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "type": self.project_type,
            "language": self.language,
            "is_ml": self.is_ml_project,
            "entry_points": self.entry_points,
        }


class ProjectDetector:
    """Detects the type and characteristics of a project directory."""

    ML_INDICATORS: Set[str] = {
        "model.pkl", "model.pth", "model.pt", "model.h5",
        "model.onnx", "model.tflite", "model.bin",
        "dataset.csv", "train.py", "predict.py",
        "notebook.ipynb",
    }

    def detect(self, root: Path) -> ProjectInfo:
        """Detect project type from directory contents."""
        root = root.resolve()
        files = set()
        extensions = set()

        for item in root.iterdir():
            if item.is_file():
                files.add(item.name.lower())
                extensions.add(item.suffix.lower())

        info = ProjectInfo(root=root)

        # Check for Python project markers
        if "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
            info.project_type = "python"
            info.language = "python"
            info.has_requirements = "requirements.txt" in files
            info.has_pyproject = "pyproject.toml" in files
            info.has_setup_py = "setup.py" in files

        elif "package.json" in files:
            info.project_type = "node"
            info.language = "javascript"
            info.has_package_json = True

        elif ".py" in extensions:
            info.project_type = "python"
            info.language = "python"

        # Check for ML indicators
        ml_matches = files & {f.lower() for f in self.ML_INDICATORS}
        ml_extensions = extensions & {".pkl", ".pth", ".pt", ".h5", ".onnx", ".tflite"}
        if ml_matches or ml_extensions:
            info.is_ml_project = True
            if info.project_type == "python":
                info.project_type = "python_ml"

        # Find entry points
        for candidate in ["app.py", "main.py", "run.py", "manage.py", "server.py"]:
            if candidate in files:
                info.entry_points.append(candidate)

        return info
