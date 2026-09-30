"""
Unit tests for app/parsing/ Python, Config, and Reference parsers.
"""
import pytest
from pathlib import Path
from app.parsing.python_parser import PythonParser
from app.parsing.config_parser import ConfigParser
from app.parsing.reference_detector import ReferenceDetector


def test_python_parser_imports_and_loads(tmp_path):
    code_file = tmp_path / "main.py"
    code_file.write_text("""
import os
import json
from pathlib import Path
import utils

def main():
    with open('dataset.csv', 'r') as f:
        data = f.read()
    model = torch.load('model.pkl')
""", encoding="utf-8")

    parser = PythonParser(project_root=tmp_path)
    result = parser.parse_file(code_file)

    imports = result["imports"]
    modules = [imp["module"] for imp in imports]
    assert "os" in modules
    assert "json" in modules
    assert "utils" in modules

    file_refs = result["file_references"]
    ref_paths = [ref["path"] for ref in file_refs]
    assert "dataset.csv" in ref_paths
    assert "model.pkl" in ref_paths


def test_config_parser_json_and_requirements(tmp_path):
    parser = ConfigParser()

    req_file = tmp_path / "requirements.txt"
    req_file.write_text("""
numpy>=1.20.0
pandas==1.5.3
# comment line
scikit-learn
""", encoding="utf-8")

    req_res = parser.parse_file(req_file)
    pkgs = [p["name"] for p in req_res.get("packages", [])]
    assert "numpy" in pkgs
    assert "pandas" in pkgs
    assert "scikit-learn" in pkgs

    json_file = tmp_path / "config.json"
    json_file.write_text('{"model": "weights.bin", "dataset": "data.csv"}', encoding="utf-8")

    json_res = parser.parse_file(json_file)
    refs = [r["value"] for r in json_res.get("file_refs", [])]
    assert "weights.bin" in refs
    assert "data.csv" in refs


def test_reference_detector(tmp_path):
    known_filenames = {"model.pkl", "dataset.csv", "config.json"}
    detector = ReferenceDetector(known_filenames=known_filenames)

    text_file = tmp_path / "readme.md"
    text_file.write_text("This script uses model.pkl and reads data from dataset.csv.", encoding="utf-8")

    matches = detector.scan_file_for_known_names(text_file)
    target_names = [m["target"] for m in matches]
    assert "model.pkl" in target_names
    assert "dataset.csv" in target_names
