"""
Unit tests for app/graph/builder.py
"""
import pytest
from pathlib import Path
from app.graph.models import (
    GraphNode, GraphEdge, EdgeType, NodeType, EvidenceItem, ConfidenceLevel
)
from app.graph.builder import StateGraph, GraphBuilder


def test_state_graph_node_and_edge_management():
    graph = StateGraph()
    node_a = GraphNode(node_id="/path/a.py", name="a.py", path="/path/a.py", node_type=NodeType.SCRIPT)
    node_b = GraphNode(node_id="/path/b.py", name="b.py", path="/path/b.py", node_type=NodeType.SCRIPT)

    graph.add_node(node_a)
    graph.add_node(node_b)

    assert graph.node_count == 2
    assert graph.get_node("/path/a.py") == node_a
    assert graph.find_node_by_name("A.PY") == node_a
    assert len(graph.find_nodes_by_name("b.py")) == 1

    evidence_1 = EvidenceItem(source_path="/path/a.py", target_path="/path/b.py", relation=EdgeType.IMPORTS, method="ast")
    edge_1 = GraphEdge(source_id="/path/a.py", target_id="/path/b.py", edge_type=EdgeType.IMPORTS, evidence=[evidence_1])
    graph.add_edge(edge_1)

    assert graph.edge_count == 1

    # Adding duplicate edge key merges evidence
    evidence_2 = EvidenceItem(source_path="/path/a.py", target_path="/path/b.py", relation=EdgeType.IMPORTS, method="string")
    edge_2 = GraphEdge(source_id="/path/a.py", target_id="/path/b.py", edge_type=EdgeType.IMPORTS, evidence=[evidence_2])
    graph.add_edge(edge_2)

    assert graph.edge_count == 1
    assert len(graph.edges[0].evidence) == 2


def test_state_graph_dependents_and_dependencies():
    graph = StateGraph()
    node_app = GraphNode(node_id="app.py", name="app.py", path="app.py", node_type=NodeType.SCRIPT)
    node_utils = GraphNode(node_id="utils.py", name="utils.py", path="utils.py", node_type=NodeType.SCRIPT)
    node_model = GraphNode(node_id="model.pkl", name="model.pkl", path="model.pkl", node_type=NodeType.FILE)

    graph.add_node(node_app)
    graph.add_node(node_utils)
    graph.add_node(node_model)

    # app.py imports utils.py
    graph.add_edge(GraphEdge(source_id="app.py", target_id="utils.py", edge_type=EdgeType.IMPORTS))
    # utils.py loads model.pkl
    graph.add_edge(GraphEdge(source_id="utils.py", target_id="model.pkl", edge_type=EdgeType.LOADS))

    # Dependencies of app.py -> utils.py
    deps_app = graph.get_dependencies("app.py")
    assert len(deps_app) == 1
    assert deps_app[0][1].node_id == "utils.py"

    # Dependents of model.pkl -> utils.py
    deps_model = graph.get_dependents("model.pkl")
    assert len(deps_model) == 1
    assert deps_model[0][1].node_id == "utils.py"


def test_state_graph_transitive_all_affected():
    graph = StateGraph()
    # Chain: app.py -> utils.py -> model.pkl
    # If model.pkl is changed/deleted, dependents are utils.py (depth 1) and app.py (depth 2)
    node_app = GraphNode(node_id="app.py", name="app.py", path="app.py", node_type=NodeType.SCRIPT)
    node_utils = GraphNode(node_id="utils.py", name="utils.py", path="utils.py", node_type=NodeType.SCRIPT)
    node_model = GraphNode(node_id="model.pkl", name="model.pkl", path="model.pkl", node_type=NodeType.FILE)

    graph.add_node(node_app)
    graph.add_node(node_utils)
    graph.add_node(node_model)

    graph.add_edge(GraphEdge(source_id="app.py", target_id="utils.py", edge_type=EdgeType.IMPORTS))
    graph.add_edge(GraphEdge(source_id="utils.py", target_id="model.pkl", edge_type=EdgeType.LOADS))

    affected = graph.get_all_affected("model.pkl")
    assert len(affected) == 2
    node_ids = [node.node_id for _, node, depth in affected]
    assert "utils.py" in node_ids
    assert "app.py" in node_ids


def test_graph_builder_builds_from_fixture():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "sample_project"
    builder = GraphBuilder(project_root=fixture_dir)
    graph = builder.build()

    assert graph.node_count >= 5
    app_node = graph.find_node_by_name("app.py")
    assert app_node is not None

    model_node = graph.find_node_by_name("model.pkl")
    assert model_node is not None

    # Verify app.py has dependencies or references
    dependents_of_model = graph.get_dependents(model_node.node_id)
    assert len(dependents_of_model) >= 1
