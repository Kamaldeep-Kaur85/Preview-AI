"""
app/safety/policy.py

Safety policies and approval logic.
Prevents unauthorized operations and enforces the approval gate.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Set

from app.graph.models import StructuredAction, RiskLevel


# System-critical paths that must NEVER be modified
BLOCKED_PATHS: Set[str] = {
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\Users\\Public",
}

# Extensions that are always high-risk to delete
HIGH_RISK_EXTENSIONS: Set[str] = {
    ".py", ".pyx", ".c", ".cpp", ".h", ".rs", ".go",
    ".java", ".cs", ".js", ".ts",
    ".sql", ".db", ".sqlite",
}


class SafetyPolicy:
    """
    Enforces safety rules before execution.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def validate_action(self, action: StructuredAction) -> tuple[bool, str]:
        """
        Validate whether an action is allowed.
        Returns (is_allowed, reason).
        """
        if not action.is_valid():
            return False, f"Invalid action: operation={action.operation}, target={action.target}"

        # Check for blocked paths
        target_path = Path(action.target)
        for blocked in BLOCKED_PATHS:
            try:
                if target_path.resolve().is_relative_to(Path(blocked)):
                    return False, f"BLOCKED: Cannot modify system path: {blocked}"
            except (ValueError, OSError):
                pass

        # Check target is within project scope
        try:
            target_resolved = target_path.resolve() if target_path.is_absolute() else (self.project_root / action.target).resolve()
            is_in_scope = (target_resolved == self.project_root or self.project_root in target_resolved.parents)
            if not is_in_scope:
                # Allow if user provided just a filename (will be resolved later)
                if not target_path.is_absolute() and "/" not in action.target and "\\" not in action.target:
                    pass  # Filename only — will be resolved in context
                else:
                    return False, f"Target is outside project scope: {target_resolved}"
        except (ValueError, OSError):
            pass

        return True, "Action is valid"

    def assess_risk_level(self, action: StructuredAction) -> RiskLevel:
        """Assess the risk level of an action based on policies."""
        target_ext = Path(action.target).suffix.lower()

        if action.operation == "DELETE":
            if target_ext in HIGH_RISK_EXTENSIONS:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM
        elif action.operation in ("MOVE", "RENAME"):
            if target_ext in HIGH_RISK_EXTENSIONS:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW
        elif action.operation == "MODIFY":
            return RiskLevel.MEDIUM
        elif action.operation == "CREATE":
            return RiskLevel.LOW

        return RiskLevel.UNKNOWN

    def check_state_freshness(self, action_timestamp: float, current_timestamp: float, max_age_seconds: float = 60.0) -> tuple[bool, str]:
        """
        Check if the simulation state is still fresh enough to execute.
        If the state is stale, execution should be blocked and re-analysis required.
        """
        age = current_timestamp - action_timestamp
        if age > max_age_seconds:
            return False, f"Preview is stale ({age:.0f}s old). Re-run simulation before executing."
        return True, "State is fresh"
