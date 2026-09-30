"""
Unit tests for app/consequence/analyzer.py
"""
import pytest
from app.graph.models import (
    GraphNode, GraphEdge, EdgeType, NodeType, RiskLevel, ConfidenceLevel, StructuredAction, EvidenceItem
)
from app.graph.builder import StateGraph
from app.simulation.simulator import Simulator
from app.consequence.analyzer import ConsequenceAnalyzer


@pytest.fixture
def dependency_graph():
    graph = StateGraph()
    node_app = GraphNode(node_id="/app/app.py", name="app.py", path="/app/app.py", node_type=NodeType.SCRIPT)
    node_utils = GraphNode(node_id="/app/utils.py", name="utils.py", path="/app/utils.py", node_type=NodeType.SCRIPT)
    node_model = GraphNode(node_id="/app/model.pkl", name="model.pkl", path="/app/model.pkl", node_type=NodeType.FILE)

    graph.add_node(node_app)
    graph.add_node(node_utils)
    graph.add_node(node_model)

    # app.py imports utils.py
    ev1 = EvidenceItem(source_path="/app/app.py", target_path="/app/utils.py", relation=EdgeType.IMPORTS, method="ast_import")
    graph.add_edge(GraphEdge(source_id="/app/app.py", target_id="/app/utils.py", edge_type=EdgeType.IMPORTS, evidence=[ev1]))

    # utils.py loads model.pkl
    ev2 = EvidenceItem(source_path="/app/utils.py", target_path="/app/model.pkl", relation=EdgeType.LOADS, method="ast_file_reference")
    graph.add_edge(GraphEdge(source_id="/app/utils.py", target_id="/app/model.pkl", edge_type=EdgeType.LOADS, evidence=[ev2]))

    return graph


def test_consequence_analyzer_delete_model(dependency_graph):
    simulator = Simulator(dependency_graph)
    action = StructuredAction(operation="DELETE", target="model.pkl")
    sim_result = simulator.simulate(action)

    analyzer = ConsequenceAnalyzer(dependency_graph)
    analysis = analyzer.analyze(sim_result)

    assert len(analysis.direct) == 1
    assert analysis.direct[0].affected_node_id == "/app/model.pkl"

    # utils.py directly loads model.pkl -> dependency impact
    assert len(analysis.dependency) == 1
    assert analysis.dependency[0].affected_node_id == "/app/utils.py"
    assert analysis.dependency[0].risk_level == RiskLevel.HIGH

    # app.py indirectly depends on model.pkl via utils.py -> secondary impact
    assert len(analysis.secondary) == 1
    assert analysis.secondary[0].affected_node_id == "/app/app.py"

    assert analysis.overall_risk == RiskLevel.HIGH
    assert analysis.total_affected == 3


def test_consequence_analyzer_target_not_found(dependency_graph):
    simulator = Simulator(dependency_graph)
    action = StructuredAction(operation="DELETE", target="missing.py")
    sim_result = simulator.simulate(action)

    analyzer = ConsequenceAnalyzer(dependency_graph)
    analysis = analyzer.analyze(sim_result)

    assert len(analysis.direct) == 0
    assert len(analysis.uncertain) == 1
    assert analysis.uncertain[0].confidence == ConfidenceLevel.UNCERTAIN
    assert analysis.overall_risk == RiskLevel.UNKNOWN


def test_consequence_analyzer_modify_action(dependency_graph):
    simulator = Simulator(dependency_graph)
    action = StructuredAction(operation="MODIFY", target="utils.py")
    sim_result = simulator.simulate(action)

    analyzer = ConsequenceAnalyzer(dependency_graph)
    analysis = analyzer.analyze(sim_result)

    assert len(analysis.direct) == 1
    assert len(analysis.dependency) == 1  # app.py depends on utils.py
    assert analysis.dependency[0].risk_level == RiskLevel.MEDIUM
    assert analysis.overall_risk == RiskLevel.MEDIUM


def test_consequence_analyzer_delete_dataset_folder():
    graph = StateGraph()
    node_folder = GraphNode(node_id="/proj/dataset", name="dataset", path="/proj/dataset", node_type=NodeType.FOLDER)
    node_data = GraphNode(node_id="/proj/dataset/heart.csv", name="heart.csv", path="/proj/dataset/heart.csv", node_type=NodeType.FILE)
    node_train = GraphNode(node_id="/proj/train.py", name="train.py", path="/proj/train.py", node_type=NodeType.SCRIPT)

    graph.add_node(node_folder)
    graph.add_node(node_data)
    graph.add_node(node_train)

    # Containment: dataset CONTAINS heart.csv
    graph.add_edge(GraphEdge(source_id="/proj/dataset", target_id="/proj/dataset/heart.csv", edge_type=EdgeType.CONTAINS))

    # train.py reads heart.csv
    ev = EvidenceItem(source_path="/proj/train.py", target_path="/proj/dataset/heart.csv", relation=EdgeType.READS, method="ast_call", line_number=12)
    graph.add_edge(GraphEdge(source_id="/proj/train.py", target_id="/proj/dataset/heart.csv", edge_type=EdgeType.READS, evidence=[ev]))

    analyzer = ConsequenceAnalyzer(graph)
    impact = analyzer.compute_impact("dataset", "DELETE")

    # Risk should be HIGH
    assert impact.risk == RiskLevel.HIGH
    # train.py must be in affected_files
    aff_names = [f.name for f in impact.affected_files]
    assert "train.py" in aff_names
    # Direct impacts must include dataset and heart.csv
    direct_names = [f.name for f in impact.direct_impacts]
    assert "dataset" in direct_names
    assert "heart.csv" in direct_names


def test_consequence_analyzer_rename_dataset_folder():
    graph = StateGraph()
    node_folder = GraphNode(node_id="/proj/dataset", name="dataset", path="/proj/dataset", node_type=NodeType.FOLDER)
    node_data = GraphNode(node_id="/proj/dataset/heart.csv", name="heart.csv", path="/proj/dataset/heart.csv", node_type=NodeType.FILE)
    node_train = GraphNode(node_id="/proj/train.py", name="train.py", path="/proj/train.py", node_type=NodeType.SCRIPT)
    node_app = GraphNode(node_id="/proj/app.py", name="app.py", path="/proj/app.py", node_type=NodeType.SCRIPT)

    graph.add_node(node_folder)
    graph.add_node(node_data)
    graph.add_node(node_train)
    graph.add_node(node_app)

    # Containment: dataset CONTAINS heart.csv
    graph.add_edge(GraphEdge(source_id="/proj/dataset", target_id="/proj/dataset/heart.csv", edge_type=EdgeType.CONTAINS))

    # train.py reads heart.csv
    ev = EvidenceItem(source_path="/proj/train.py", target_path="/proj/dataset/heart.csv", relation=EdgeType.READS, method="ast_call", line_number=12)
    graph.add_edge(GraphEdge(source_id="/proj/train.py", target_id="/proj/dataset/heart.csv", edge_type=EdgeType.READS, evidence=[ev]))

    analyzer = ConsequenceAnalyzer(graph)
    impact = analyzer.compute_impact("dataset", "RENAME", destination="dataset_renamed")

    # Risk should be HIGH
    assert impact.risk == RiskLevel.HIGH
    aff_names = [f.name for f in impact.affected_files]
    assert "train.py" in aff_names
    # app.py matches the dataset heuristic
    assert "app.py" in aff_names
    # Direct impacts must include dataset and heart.csv
    direct_names = [f.name for f in impact.direct_impacts]
    assert "dataset" in direct_names
    assert "heart.csv" in direct_names


def test_consequence_analyzer_create_new_component():
    graph = StateGraph()
    node_app = GraphNode(node_id="/proj/app.py", name="app.py", path="/proj/app.py", node_type=NodeType.SCRIPT)
    graph.add_node(node_app)

    analyzer = ConsequenceAnalyzer(graph)
    impact = analyzer.compute_impact("helper.py", "CREATE")

    assert impact.operation == "CREATE"
    assert impact.analysis_complete is True
    assert impact.risk in (RiskLevel.NO_CONFIRMED_IMPACT, RiskLevel.LOW)
    assert len(impact.direct_impacts) == 1
    assert impact.direct_impacts[0].name == "helper.py"



