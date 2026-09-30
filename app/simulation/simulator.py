"""
app/simulation/simulator.py

Simulation engine: applies a structured action to a virtual state
and computes the diff between before and after.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.graph.models import GraphNode, StructuredAction
from app.graph.builder import StateGraph
from app.simulation.virtual_state import VirtualState


class SimulationResult:
    """Result of a simulation run."""

    def __init__(
        self,
        action: StructuredAction,
        before_state: Dict[str, GraphNode],
        after_state: VirtualState,
        graph: StateGraph,
        simulation_time_ms: float = 0.0,
    ):
        self.action = action
        self.before_state = before_state
        self.after_state = after_state
        self.graph = graph
        self.simulation_time_ms = simulation_time_ms

    @property
    def removed_nodes(self) -> Dict[str, GraphNode]:
        return self.after_state.get_removed_nodes()

    @property
    def changes(self) -> List[dict]:
        return self.after_state.get_changes_summary()

    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict(),
            "changes": self.changes,
            "removed_count": len(self.removed_nodes),
            "simulation_time_ms": self.simulation_time_ms,
        }


class Simulator:
    """
    Applies a StructuredAction to a virtual copy of the state graph.
    Never modifies the real filesystem.
    """

    def __init__(self, graph: StateGraph):
        self.graph = graph

    def simulate(self, action: StructuredAction) -> SimulationResult:
        """Simulate an action and return the result."""
        start = time.monotonic()

        # Create virtual state from current graph nodes
        virtual = VirtualState(self.graph.nodes)
        before_state = {k: v for k, v in self.graph.nodes.items()}

        # Resolve target
        target_node = self._resolve_target(action.target)
        if not target_node:
            if action.operation == "CREATE":
                virtual.create(action.target)
            elapsed = (time.monotonic() - start) * 1000
            return SimulationResult(
                action=action,
                before_state=before_state,
                after_state=virtual,
                graph=self.graph,
                simulation_time_ms=elapsed,
            )

        # Apply the operation
        if action.operation == "DELETE":
            virtual.delete(target_node.node_id)
        elif action.operation == "MOVE":
            if action.destination:
                virtual.move(target_node.node_id, action.destination)
        elif action.operation == "RENAME":
            if action.destination:
                virtual.rename(target_node.node_id, action.destination)
        elif action.operation == "MODIFY":
            virtual.modify(target_node.node_id, description=action.raw_intent)
        elif action.operation == "CREATE":
            virtual.create(action.target)

        elapsed = (time.monotonic() - start) * 1000
        return SimulationResult(
            action=action,
            before_state=before_state,
            after_state=virtual,
            graph=self.graph,
            simulation_time_ms=elapsed,
        )

    def _resolve_target(self, target: str) -> Optional[GraphNode]:
        """Resolve a target string to a graph node."""
        # Try exact path match
        node = self.graph.get_node(target)
        if node:
            return node

        # Try as absolute path
        try:
            abs_path = Path(target).resolve()
            node = self.graph.get_node(str(abs_path))
            if node:
                return node
        except Exception:
            pass

        # Try by filename
        node = self.graph.find_node_by_name(target)
        if node:
            return node

        # Try partial path match
        target_lower = target.lower().replace("\\", "/")
        target_suffix = "/" + target_lower if not target_lower.startswith("/") else target_lower
        for node_id, node in self.graph.nodes.items():
            norm_id = node_id.lower().replace("\\", "/")
            if norm_id.endswith(target_suffix) or norm_id == target_lower:
                return node

        # Try stem match (e.g. "dataset" matching "dataset.csv" or "dataset.parquet")
        target_stem = Path(target_lower.strip("/")).name
        for node_id, node in self.graph.nodes.items():
            if Path(node.name).stem.lower() == target_stem:
                return node

        # Check if target exists on disk as a folder/file within project
        try:
            p = Path(target)
            if not p.is_absolute():
                proj = getattr(self.graph, "project_root", None)
                if proj:
                    cand = Path(proj) / target
                    if cand.exists():
                        p = cand
            if p.exists():
                return GraphNode.from_path(p.resolve())
        except Exception:
            pass

        return None
