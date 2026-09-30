"""
Integration tests for the complete PreView AI simulation & consequence prediction pipeline.
"""
import pytest
from pathlib import Path
from app.graph.builder import GraphBuilder
from app.graph.models import StructuredAction, RiskLevel, ConfidenceLevel
from app.simulation.simulator import Simulator
from app.consequence.analyzer import ConsequenceAnalyzer
from app.safety.policy import SafetyPolicy


@pytest.fixture
def fixture_project_root():
    return Path(__file__).parent.parent / "fixtures" / "sample_project"


def test_full_end_to_end_delete_model_simulation(fixture_project_root):
    # 1. Build State Graph
    builder = GraphBuilder(project_root=fixture_project_root)
    graph = builder.build()

    assert graph.node_count >= 5
    assert graph.edge_count >= 2

    # 2. Define Action
    action = StructuredAction(
        operation="DELETE",
        target="model.pkl",
        scope="single_file",
        raw_intent="Delete the model.pkl file",
    )

    # 3. Validate Safety Policy
    policy = SafetyPolicy(project_root=fixture_project_root)
    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is True

    # 4. Simulate Action
    simulator = Simulator(graph)
    sim_result = simulator.simulate(action)

    assert len(sim_result.removed_nodes) == 1
    assert len(sim_result.changes) == 1
    assert sim_result.changes[0]["type"] == "DELETE"

    # 5. Analyze Consequences
    analyzer = ConsequenceAnalyzer(graph)
    analysis = analyzer.analyze(sim_result)

    assert analysis.total_affected >= 2
    assert analysis.overall_risk == RiskLevel.HIGH

    # Check direct impact
    assert len(analysis.direct) == 1
    assert analysis.direct[0].affected_node_name == "model.pkl"

    # Check dependency impacts (app.py and/or config.json depend on model.pkl)
    affected_names = [item.affected_node_name for item in analysis.all_consequences]
    assert "app.py" in affected_names or "config.json" in affected_names


def test_full_end_to_end_move_script_simulation(fixture_project_root):
    builder = GraphBuilder(project_root=fixture_project_root)
    graph = builder.build()

    action = StructuredAction(
        operation="MOVE",
        target="utils.py",
        destination=str(fixture_project_root / "helpers" / "utils.py"),
        raw_intent="Move utils.py to helpers directory",
    )

    simulator = Simulator(graph)
    sim_result = simulator.simulate(action)

    analyzer = ConsequenceAnalyzer(graph)
    analysis = analyzer.analyze(sim_result)

    assert analysis.total_affected >= 1
    affected_names = [item.affected_node_name for item in analysis.all_consequences]
    assert "utils.py" in affected_names
