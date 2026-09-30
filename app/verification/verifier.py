"""
app/verification/verifier.py

Verification engine: compares predicted state with actual state after execution.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Dict, List, Optional

from app.graph.models import GraphNode, StructuredAction
from app.graph.builder import GraphBuilder, StateGraph
from app.simulation.simulator import SimulationResult


class VerificationResult:
    """Result of verifying predicted vs actual state."""

    MATCH = "MATCH"
    PARTIAL = "PARTIAL_MATCH"
    MISMATCH = "MISMATCH"

    def __init__(
        self,
        action: StructuredAction,
        status: str,
        matches: List[dict],
        mismatches: List[dict],
        verification_time_ms: float = 0.0,
    ):
        self.action = action
        self.status = status
        self.matches = matches
        self.mismatches = mismatches
        self.verification_time_ms = verification_time_ms

    @property
    def is_match(self) -> bool:
        return self.status == self.MATCH

    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict(),
            "status": self.status,
            "matches": self.matches,
            "mismatches": self.mismatches,
            "verification_time_ms": self.verification_time_ms,
        }


class Verifier:
    """
    Compares predicted state (from simulation) with actual state
    (from re-scanning the filesystem after execution).
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def verify(self, sim_result: SimulationResult) -> VerificationResult:
        """Verify simulation predictions against actual state."""
        start = time.monotonic()

        # Re-scan the project to get actual state
        builder = GraphBuilder(self.project_root)
        actual_graph = builder.build()

        matches = []
        mismatches = []

        # Check each change from the simulation
        for change in sim_result.changes:
            change_type = change["type"]
            target_id = change["target"]
            target_name = change.get("name", Path(target_id).name)

            if change_type == "DELETE":
                # Predicted: target should not exist
                actual_node = actual_graph.find_node_by_name(target_name)
                if actual_node is None or not actual_node.exists:
                    matches.append({
                        "prediction": f"{target_name} removed",
                        "actual": f"{target_name} removed",
                        "status": "MATCH",
                    })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} removed",
                        "actual": f"{target_name} still exists",
                        "status": "MISMATCH",
                    })

            elif change_type == "MOVE":
                new_path = change.get("new_path", "")
                if Path(new_path).exists():
                    matches.append({
                        "prediction": f"{target_name} moved to {new_path}",
                        "actual": f"File exists at {new_path}",
                        "status": "MATCH",
                    })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} moved to {new_path}",
                        "actual": f"File not found at {new_path}",
                        "status": "MISMATCH",
                    })

            elif change_type == "RENAME":
                new_path = change.get("new_path", "")
                if Path(new_path).exists():
                    matches.append({
                        "prediction": f"{target_name} renamed",
                        "actual": "Rename verified",
                        "status": "MATCH",
                    })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} renamed",
                        "actual": "Rename not verified",
                        "status": "MISMATCH",
                    })

            elif change_type == "MODIFY":
                target_p = Path(target_id) if Path(target_id).is_absolute() else (self.project_root / target_id)
                if not target_p.exists():
                    node = actual_graph.find_node_by_name(target_name)
                    if node:
                        target_p = Path(node.path)

                if target_p.exists() and target_p.is_file():
                    syntax_ok = True
                    syntax_err = ""
                    if target_p.suffix.lower() == ".py":
                        try:
                            import ast
                            ast.parse(target_p.read_text(encoding="utf-8", errors="replace"))
                        except SyntaxError as e:
                            syntax_ok = False
                            syntax_err = str(e)

                    if syntax_ok:
                        matches.append({
                            "prediction": f"{target_name} modified",
                            "actual": f"{target_name} modified on disk (syntax valid)",
                            "status": "MATCH",
                        })
                    else:
                        mismatches.append({
                            "prediction": f"{target_name} modified",
                            "actual": f"Syntax error in modified file: {syntax_err}",
                            "status": "MISMATCH",
                        })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} modified",
                        "actual": f"Target file does not exist: {target_name}",
                        "status": "MISMATCH",
                    })

            elif change_type in ("CREATE", "CREATE_FOLDER"):
                target_p = Path(target_id) if Path(target_id).is_absolute() else (self.project_root / target_id)
                actual_node = actual_graph.find_node_by_name(target_name)
                if target_p.exists() or (actual_node and actual_node.exists):
                    matches.append({
                        "prediction": f"{target_name} created",
                        "actual": f"{target_name} exists on disk",
                        "status": "MATCH",
                    })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} created",
                        "actual": f"{target_name} not found on disk",
                        "status": "MISMATCH",
                    })

            elif change_type == "COPY":
                new_path = change.get("new_path", "")
                if Path(new_path).exists():
                    matches.append({
                        "prediction": f"{target_name} copied to {new_path}",
                        "actual": f"Copy exists at {new_path}",
                        "status": "MATCH",
                    })
                else:
                    mismatches.append({
                        "prediction": f"{target_name} copied to {new_path}",
                        "actual": f"Copy not found at {new_path}",
                        "status": "MISMATCH",
                    })

        # Also check dependency impacts
        target_node_sim = sim_result.graph.get_node(sim_result.action.target) or sim_result.graph.find_node_by_name(sim_result.action.target)
        target_id_sim = target_node_sim.node_id if target_node_sim else sim_result.action.target

        for edge, dep_node in sim_result.graph.get_dependents(target_id_sim):
            dep_name = dep_node.name
            actual_dep = actual_graph.find_node_by_name(dep_name)
            if actual_dep:
                # Check if the dependency edge still exists in actual
                actual_deps = actual_graph.get_dependencies(actual_dep.node_id)
                target_name_sim = Path(sim_result.action.target).name
                broken = True
                for _, tgt_node in actual_deps:
                    if tgt_node.name == target_name_sim:
                        broken = False
                        break
                if broken:
                    matches.append({
                        "prediction": f"{dep_name} dependency on {target_name_sim} affected",
                        "actual": f"{dep_name} dependency on {target_name_sim} affected",
                        "status": "MATCH",
                    })

        # Determine overall status
        if not mismatches:
            status = VerificationResult.MATCH
        elif matches and mismatches:
            status = VerificationResult.PARTIAL
        else:
            status = VerificationResult.MISMATCH

        elapsed = (time.monotonic() - start) * 1000
        return VerificationResult(
            action=sim_result.action,
            status=status,
            matches=matches,
            mismatches=mismatches,
            verification_time_ms=elapsed,
        )

    def verify_paths(self, affected_paths: List[str], operation: str) -> bool:
        """Directly verify affected paths on disk according to operation semantics."""
        if not affected_paths:
            return True
        for p_str in affected_paths:
            p = Path(p_str)
            if operation == "DELETE":
                if p.exists():
                    return False
            elif operation in ("CREATE", "CREATE_FOLDER", "MOVE", "RENAME", "COPY"):
                if not p.exists():
                    return False
            elif operation in ("MODIFY", "EDIT"):
                if not p.exists() or not p.is_file():
                    return False
                if p.suffix.lower() == ".py":
                    try:
                        import ast
                        ast.parse(p.read_text(encoding="utf-8", errors="replace"))
                    except SyntaxError:
                        return False
        return True
