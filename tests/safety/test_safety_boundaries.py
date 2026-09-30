"""
tests/safety/test_safety_boundaries.py

Comprehensive security and safety policy tests for PreView AI.
Ensures destructive actions outside the monitored root are strictly rejected,
system paths are protected, and freshness policies prevent stale executions.
"""
import pytest
import time
from pathlib import Path
from app.graph.models import StructuredAction, RiskLevel
from app.safety.policy import SafetyPolicy, BLOCKED_PATHS, HIGH_RISK_EXTENSIONS


def test_safety_blocks_path_traversal(tmp_path):
    project_root = tmp_path / "my_project"
    project_root.mkdir()
    policy = SafetyPolicy(project_root=project_root)

    # Relative path traversal trying to escape project root
    traversal_action = StructuredAction(
        operation="DELETE",
        target="../../important_system_file.py"
    )
    allowed, reason = policy.validate_action(traversal_action)
    assert allowed is False
    assert "outside project scope" in reason


def test_safety_blocks_windows_system_directories(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)

    for sys_dir in BLOCKED_PATHS:
        bad_action = StructuredAction(
            operation="DELETE",
            target=f"{sys_dir}\\critical_payload.dll"
        )
        allowed, reason = policy.validate_action(bad_action)
        assert allowed is False
        assert "BLOCKED" in reason or "outside project scope" in reason


def test_safety_blocks_empty_and_unknown_operations(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)

    empty_target = StructuredAction(operation="DELETE", target="")
    allowed, _ = policy.validate_action(empty_target)
    assert allowed is False

    unknown_op = StructuredAction(operation="EXECUTE_ARBITRARY_CMD", target="test.py")
    allowed, _ = policy.validate_action(unknown_op)
    assert allowed is False


def test_safety_risk_classification(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)

    for ext in HIGH_RISK_EXTENSIONS:
        del_action = StructuredAction(operation="DELETE", target=f"module{ext}")
        assert policy.assess_risk_level(del_action) == RiskLevel.HIGH

        move_action = StructuredAction(operation="MOVE", target=f"module{ext}", destination="new_loc")
        assert policy.assess_risk_level(move_action) == RiskLevel.MEDIUM

    txt_action = StructuredAction(operation="DELETE", target="notes.txt")
    assert policy.assess_risk_level(txt_action) == RiskLevel.MEDIUM


def test_safety_state_freshness_rejection(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)
    now = time.monotonic()

    # Immediate check is fresh
    is_fresh, msg = policy.check_state_freshness(action_timestamp=now, current_timestamp=now + 5, max_age_seconds=30)
    assert is_fresh is True
    assert "fresh" in msg.lower()

    # Beyond threshold is stale
    is_fresh, msg = policy.check_state_freshness(action_timestamp=now, current_timestamp=now + 31, max_age_seconds=30)
    assert is_fresh is False
    assert "stale" in msg.lower()
