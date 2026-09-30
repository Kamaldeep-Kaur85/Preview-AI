"""
Unit tests for app/simulation/virtual_state.py
"""
import pytest
from app.graph.models import GraphNode, NodeType
from app.simulation.virtual_state import VirtualState


def test_virtual_state_copy_on_write_isolation():
    node_1 = GraphNode(node_id="/path/a.py", name="a.py", path="/path/a.py", node_type=NodeType.SCRIPT)
    original_nodes = {node_1.node_id: node_1}

    v_state = VirtualState(original_nodes)
    v_state.delete(node_1.node_id)

    # Virtual state should show node deleted
    assert v_state.nodes[node_1.node_id].exists is False
    assert len(v_state.get_existing_nodes()) == 0
    assert len(v_state.get_removed_nodes()) == 1

    # Original node object MUST NOT be mutated
    assert original_nodes[node_1.node_id].exists is True


def test_virtual_state_move():
    node_1 = GraphNode(node_id="/path/a.py", name="a.py", path="/path/a.py", node_type=NodeType.SCRIPT)
    original_nodes = {node_1.node_id: node_1}

    v_state = VirtualState(original_nodes)
    success = v_state.move(node_1.node_id, "/path/b.py")
    assert success is True

    # Old path should be marked deleted
    assert v_state.nodes["/path/a.py"].exists is False
    # New path should exist
    assert "/path/b.py" in v_state.nodes
    assert v_state.nodes["/path/b.py"].exists is True
    assert v_state.nodes["/path/b.py"].name == "b.py"

    changes = v_state.get_changes_summary()
    assert len(changes) == 1
    assert changes[0]["type"] == "MOVE"
    assert changes[0]["old_path"] == "/path/a.py"
    assert changes[0]["new_path"] == "/path/b.py"


def test_virtual_state_rename():
    node_1 = GraphNode(node_id="/path/old_name.py", name="old_name.py", path="/path/old_name.py", node_type=NodeType.SCRIPT)
    original_nodes = {node_1.node_id: node_1}

    v_state = VirtualState(original_nodes)
    success = v_state.rename(node_1.node_id, "new_name.py")
    assert success is True

    assert v_state.nodes["/path/old_name.py"].exists is False
    assert "/path/new_name.py" in v_state.nodes
    assert v_state.nodes["/path/new_name.py"].name == "new_name.py"


def test_virtual_state_modify():
    node_1 = GraphNode(node_id="/path/config.json", name="config.json", path="/path/config.json", node_type=NodeType.CONFIG)
    original_nodes = {node_1.node_id: node_1}

    v_state = VirtualState(original_nodes)
    success = v_state.modify(node_1.node_id, description="Updated config key")
    assert success is True

    assert v_state.nodes[node_1.node_id].metadata.get("modified_in_simulation") is True
    changes = v_state.get_changes_summary()
    assert len(changes) == 1
    assert changes[0]["type"] == "MODIFY"
