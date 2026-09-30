"""
Unit tests for app/safety/policy.py
"""
import pytest
import time
from pathlib import Path
from app.graph.models import StructuredAction, RiskLevel
from app.safety.policy import SafetyPolicy, BLOCKED_PATHS


def test_safety_policy_valid_action(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)
    target_file = tmp_path / "app.py"
    target_file.write_text("print(1)", encoding="utf-8")

    action = StructuredAction(operation="DELETE", target=str(target_file))
    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is True
    assert "Action is valid" in reason


def test_safety_policy_invalid_action(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)
    action = StructuredAction(operation="INVALID_OP", target="app.py")
    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is False
    assert "Invalid action" in reason


def test_safety_policy_blocked_system_path(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)
    blocked_target = "C:\\Windows\\System32\\cmd.exe"
    action = StructuredAction(operation="DELETE", target=blocked_target)
    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is False
    assert "BLOCKED" in reason or "outside project scope" in reason


def test_safety_policy_outside_project_scope(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("data", encoding="utf-8")

    policy = SafetyPolicy(project_root=project_dir)
    action = StructuredAction(operation="DELETE", target=str(outside_file))
    is_allowed, reason = policy.validate_action(action)
    assert is_allowed is False
    assert "outside project scope" in reason


def test_safety_policy_assess_risk_level(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)

    # Deleting python file is HIGH risk
    action_py = StructuredAction(operation="DELETE", target="script.py")
    assert policy.assess_risk_level(action_py) == RiskLevel.HIGH

    # Deleting txt file is MEDIUM risk
    action_txt = StructuredAction(operation="DELETE", target="notes.txt")
    assert policy.assess_risk_level(action_txt) == RiskLevel.MEDIUM

    # Moving python file is MEDIUM risk
    action_move_py = StructuredAction(operation="MOVE", target="script.py", destination="lib/script.py")
    assert policy.assess_risk_level(action_move_py) == RiskLevel.MEDIUM


def test_safety_policy_check_state_freshness(tmp_path):
    policy = SafetyPolicy(project_root=tmp_path)
    now = time.monotonic()

    # Fresh timestamp (10 seconds ago)
    is_fresh, reason = policy.check_state_freshness(action_timestamp=now - 10, current_timestamp=now, max_age_seconds=60)
    assert is_fresh is True
    assert "fresh" in reason.lower()

    # Stale timestamp (120 seconds ago)
    is_fresh, reason = policy.check_state_freshness(action_timestamp=now - 120, current_timestamp=now, max_age_seconds=60)
    assert is_fresh is False
    assert "stale" in reason.lower()
