"""
Unit tests for app/simulation/simulator.py
"""
import pytest
from app.graph.models import GraphNode, NodeType, StructuredAction
from app.graph.builder import StateGraph
from app.simulation.simulator import Simulator


@pytest.fixture
def sample_graph():
    graph = StateGraph()
    node_app = GraphNode(node_id="/project/app.py", name="app.py", path="/project/app.py", node_type=NodeType.SCRIPT)
    node_model = GraphNode(node_id="/project/models/model.pkl", name="model.pkl", path="/project/models/model.pkl", node_type=NodeType.FILE)

    graph.add_node(node_app)
    graph.add_node(node_model)
    return graph


def test_simulator_delete(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="DELETE", target="model.pkl")

    result = simulator.simulate(action)
    assert result.action.operation == "DELETE"
    assert len(result.removed_nodes) == 1
    assert "/project/models/model.pkl" in result.removed_nodes
    assert len(result.changes) == 1
    assert result.changes[0]["type"] == "DELETE"


def test_simulator_move(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="MOVE", target="model.pkl", destination="/project/backup/model.pkl")

    result = simulator.simulate(action)
    assert result.action.operation == "MOVE"
    assert "/project/models/model.pkl" in result.removed_nodes
    assert "/project/backup/model.pkl" in result.after_state.nodes


def test_simulator_rename(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="RENAME", target="app.py", destination="/project/main.py")

    result = simulator.simulate(action)
    assert result.action.operation == "RENAME"
    assert "/project/app.py" in result.removed_nodes
    assert "/project/main.py" in result.after_state.nodes


def test_simulator_modify(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="MODIFY", target="app.py", raw_intent="Update imports")

    result = simulator.simulate(action)
    assert result.action.operation == "MODIFY"
    assert len(result.removed_nodes) == 0
    assert result.after_state.nodes["/project/app.py"].metadata.get("modified_in_simulation") is True


def test_simulator_unknown_target(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="DELETE", target="nonexistent.txt")

    result = simulator.simulate(action)
    assert len(result.removed_nodes) == 0
    assert len(result.changes) == 0


def test_simulator_create(sample_graph):
    simulator = Simulator(sample_graph)
    action = StructuredAction(operation="CREATE", target="new_helper.py")

    result = simulator.simulate(action)
    assert result.action.operation == "CREATE"
    assert "new_helper.py" in result.after_state.nodes
    assert len(result.changes) == 1
    assert result.changes[0]["type"] == "CREATE"

