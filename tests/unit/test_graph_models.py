"""
Unit tests for app/graph/models.py
"""
import pytest
from pathlib import Path
from app.graph.models import (
    NodeType, EdgeType, RiskLevel, ConfidenceLevel,
    EvidenceItem, GraphNode, GraphEdge, ConsequenceItem, StructuredAction
)


def test_node_type_enum():
    assert NodeType.FILE.value == "FILE"
    assert NodeType.SCRIPT.value == "SCRIPT"
    assert NodeType.CONFIG.value == "CONFIG"
    assert NodeType.PACKAGE.value == "PACKAGE"


def test_edge_type_enum():
    assert EdgeType.IMPORTS.value == "IMPORTS"
    assert EdgeType.LOADS.value == "LOADS"
    assert EdgeType.READS.value == "READS"
    assert EdgeType.REFERENCES.value == "REFERENCES"


def test_evidence_item_to_dict_and_str():
    evidence = EvidenceItem(
        source_path="/app/main.py",
        target_path="/app/model.pkl",
        relation=EdgeType.LOADS,
        method="ast_file_reference",
        line_number=12,
        confidence=ConfidenceLevel.CONFIRMED,
        raw_text="torch.load('model.pkl')",
    )
    d = evidence.to_dict()
    assert d["source"] == "/app/main.py"
    assert d["target"] == "/app/model.pkl"
    assert d["relation"] == "LOADS"
    assert d["method"] == "ast_file_reference"
    assert d["line_number"] == 12
    assert d["confidence"] == "CONFIRMED"

    s = str(evidence)
    assert "main.py:12" in s
    assert "LOADS" in s
    assert "model.pkl" in s


def test_graph_node_from_path(tmp_path):
    test_file = tmp_path / "script.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    node = GraphNode.from_path(test_file)
    assert node.name == "script.py"
    assert node.node_type == NodeType.SCRIPT
    assert node.extension == ".py"
    assert node.size_bytes > 0
    assert node.exists is True

    d = node.to_dict()
    assert d["name"] == "script.py"
    assert d["node_type"] == "SCRIPT"


def test_graph_node_infer_type(tmp_path):
    py_node = GraphNode.from_path(tmp_path / "app.py")
    assert py_node.node_type == NodeType.SCRIPT

    json_node = GraphNode.from_path(tmp_path / "config.json")
    assert json_node.node_type == NodeType.CONFIG

    req_node = GraphNode.from_path(tmp_path / "requirements.txt")
    assert req_node.node_type == NodeType.CONFIG

    dir_path = tmp_path / "data"
    dir_path.mkdir()
    dir_node = GraphNode.from_path(dir_path)
    assert dir_node.node_type == NodeType.FOLDER


def test_graph_edge():
    evidence = EvidenceItem(
        source_path="a.py",
        target_path="b.py",
        relation=EdgeType.IMPORTS,
        method="ast_import",
    )
    edge = GraphEdge(
        source_id="a.py",
        target_id="b.py",
        edge_type=EdgeType.IMPORTS,
        evidence=[evidence],
        confidence=ConfidenceLevel.CONFIRMED,
    )
    assert edge.key == ("a.py", "b.py", "IMPORTS")
    d = edge.to_dict()
    assert d["source"] == "a.py"
    assert d["target"] == "b.py"
    assert len(d["evidence"]) == 1


def test_consequence_item():
    item = ConsequenceItem(
        affected_node_id="/app/app.py",
        affected_node_name="app.py",
        impact_type="dependency",
        description="app.py imports target.py",
        risk_level=RiskLevel.HIGH,
        confidence=ConfidenceLevel.CONFIRMED,
    )
    d = item.to_dict()
    assert d["affected_node"] == "app.py"
    assert d["impact_type"] == "dependency"
    assert d["risk_level"] == "HIGH"


def test_structured_action_validation():
    action_delete = StructuredAction(operation="DELETE", target="model.pkl")
    assert action_delete.is_valid() is True

    action_invalid_op = StructuredAction(operation="EXPLODE", target="model.pkl")
    assert action_invalid_op.is_valid() is False

    action_no_target = StructuredAction(operation="DELETE", target="")
    assert action_no_target.is_valid() is False

    d = action_delete.to_dict()
    assert d["operation"] == "DELETE"
    assert d["target"] == "model.pkl"
