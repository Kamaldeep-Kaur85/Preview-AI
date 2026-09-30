"""
Unit tests for Verifier, SafetyPolicy, Simulator, and Executor edge cases.
"""
from pathlib import Path
from app.graph.models import (
    GraphNode, GraphEdge, EdgeType, NodeType, RiskLevel, ConfidenceLevel, StructuredAction, EvidenceItem,
    ConsequenceItem,
)
from app.graph.builder import StateGraph
from app.simulation.simulator import Simulator, SimulationResult
from app.consequence.analyzer import ConsequenceAnalyzer, ConsequenceAnalysis
from app.verification.verifier import Verifier
from app.safety.policy import SafetyPolicy
from app.execution.executor import Executor
from app.ai.explanation import ExplanationEngine


def test_verifier_dependency_resolution(tmp_path):
    # Setup graph with full path node IDs
    graph = StateGraph()
    model_path = str(tmp_path / "model.pkl")
    app_path = str(tmp_path / "app.py")

    node_model = GraphNode(node_id=model_path, name="model.pkl", path=model_path, node_type=NodeType.FILE)
    node_app = GraphNode(node_id=app_path, name="app.py", path=app_path, node_type=NodeType.SCRIPT)

    graph.add_node(node_model)
    graph.add_node(node_app)

    ev = EvidenceItem(source_path=app_path, target_path=model_path, relation=EdgeType.LOADS, method="ast")
    graph.add_edge(GraphEdge(source_id=app_path, target_id=model_path, edge_type=EdgeType.LOADS, evidence=[ev]))

    action = StructuredAction(operation="DELETE", target="model.pkl")
    simulator = Simulator(graph)
    sim_result = simulator.simulate(action)

    verifier = Verifier(project_root=tmp_path)
    # Perform verification
    res = verifier.verify(sim_result)
    assert res.is_match or res.status == "MATCH"
    # Should have verified matches
    assert len(res.matches) >= 1


def test_safety_policy_path_boundary_security(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Path that starts with project_root string but is a sibling directory
    malicious_dir = tmp_path / "project_malicious"
    malicious_dir.mkdir()
    malicious_file = malicious_dir / "secret.py"
    malicious_file.write_text("secret")

    policy = SafetyPolicy(project_root=project_root)
    action = StructuredAction(operation="DELETE", target=str(malicious_file))

    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is False
    assert "outside project scope" in reason


def test_simulator_partial_path_match_boundary(tmp_path):
    graph = StateGraph()
    app_path = str(tmp_path / "app.py")
    node_app = GraphNode(node_id=app_path, name="app.py", path=app_path, node_type=NodeType.SCRIPT)
    graph.add_node(node_app)

    simulator = Simulator(graph)

    # Searching for just "py" shouldn't resolve to app.py
    target_node = simulator._resolve_target("py")
    assert target_node is None

    # Searching for "app.py" should resolve
    target_node_valid = simulator._resolve_target("app.py")
    assert target_node_valid is not None
    assert target_node_valid.name == "app.py"


def test_executor_rename_nested_destination(tmp_path):
    target_file = tmp_path / "old.py"
    target_file.write_text("print(1)")

    executor = Executor(project_root=tmp_path)
    action = StructuredAction(operation="RENAME", target=str(target_file), destination="subfolder/new.py")

    res = executor.execute(action)
    assert res.success is True
    assert (tmp_path / "subfolder" / "new.py").exists()


def test_explanation_engine_robustness():
    engine = ExplanationEngine()
    action = StructuredAction(operation="DELETE", target="model.pkl")

    # Item with string or enum confidence
    c1 = ConsequenceItem(
        affected_node_id="app.py",
        affected_node_name="app.py",
        impact_type="dependency",
        description="app.py depends on model.pkl",
        risk_level=RiskLevel.HIGH,
        confidence=ConfidenceLevel.CONFIRMED,
    )
    analysis = ConsequenceAnalysis(
        action=action,
        direct=[],
        dependency=[c1],
        secondary=[],
        uncertain=[],
        overall_risk=RiskLevel.HIGH,
    )

    full_exp = engine.explain(analysis)
    assert "Dependency Impact" in full_exp
    assert "app.py" in full_exp

    short_exp = engine.explain_short(analysis)
    assert "HIGH risk" in short_exp
