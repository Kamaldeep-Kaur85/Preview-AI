"""
tests/unit/test_execution_and_modification.py

Comprehensive tests for real filesystem execution, verification, and re-indexing:
1. CREATE (file with content, directory)
2. MODIFY (actual content change on disk, syntax validation, rollback on error)
3. RENAME (actual rename on disk, target verified, old path removed)
4. MOVE (actual move on disk, destination verified, source removed)
5. COPY (actual copy on disk, both exist)
6. DELETE (file and folder deletion on disk)
7. FAILED OPERATIONS (target not found, safety blocked, syntax error, no-op modification)
8. VERIFICATION (predicted vs actual disk state matches)
9. RE-INDEXING (graph reloaded, updated node and edge count verified)
"""
import ast
import os
import pytest
from pathlib import Path

from app.execution.executor import Executor, ExecutionResult
from app.graph.models import StructuredAction
from app.graph.builder import GraphBuilder
from app.simulation.simulator import Simulator
from app.verification.verifier import Verifier, VerificationResult
from app.main import PreViewAIService


@pytest.fixture
def test_project(tmp_path):
    proj = tmp_path / "sample_ml"
    proj.mkdir()
    (proj / "train.py").write_text("threshold = 0.5\ndef train_model():\n    return 'trained'\n", encoding="utf-8")
    (proj / "pipeline.py").write_text("import train\nprint(train.train_model())\n", encoding="utf-8")
    (proj / "dataset.csv").write_text("id,val\n1,10\n2,20\n", encoding="utf-8")
    sub = proj / "data"
    sub.mkdir()
    return proj


def test_execute_create_file_and_verify_disk(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="CREATE",
        target="data/new_dataset.csv",
        content="id,feature\n1,alpha\n2,beta\n",
    )
    result = executor.execute(action)
    assert result.success is True
    created_file = test_project / "data" / "new_dataset.csv"
    assert created_file.exists()
    assert created_file.is_file()
    assert created_file.read_text(encoding="utf-8") == "id,feature\n1,alpha\n2,beta\n"


def test_execute_create_folder_and_verify_disk(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="CREATE_FOLDER",
        target="checkpoints",
    )
    result = executor.execute(action)
    assert result.success is True
    created_dir = test_project / "checkpoints"
    assert created_dir.exists()
    assert created_dir.is_dir()


def test_execute_modify_file_actual_disk_content(test_project):
    """Verify that MODIFY actually changes the target file content on disk."""
    train_file = test_project / "train.py"
    original_content = train_file.read_text(encoding="utf-8")
    assert "threshold = 0.5" in original_content

    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="MODIFY",
        target="train.py",
        raw_intent="Change threshold to 0.75",
        target_value="threshold = 0.5",
        new_value="threshold = 0.75",
    )
    result = executor.execute(action)
    assert result.success is True
    assert "Successfully modified train.py" in result.message

    # Verify on actual disk
    updated_content = train_file.read_text(encoding="utf-8")
    assert "threshold = 0.75" in updated_content
    assert "threshold = 0.5" not in updated_content
    # Verify Python syntax
    ast.parse(updated_content)


def test_execute_modify_syntax_error_blocked(test_project):
    """Verify that a modification introducing invalid Python syntax is rejected and not written."""
    train_file = test_project / "train.py"
    original_content = train_file.read_text(encoding="utf-8")

    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="MODIFY",
        target="train.py",
        new_content="def invalid_syntax(\n  this is completely broken syntax !!!\n",
    )
    result = executor.execute(action)
    assert result.success is False
    assert "syntax" in result.error.lower()

    # Disk content must remain untouched
    assert train_file.read_text(encoding="utf-8") == original_content


def test_execute_modify_no_change_rejected(test_project):
    """Verify that a modification producing identical content reports failure."""
    train_file = test_project / "train.py"
    current_content = train_file.read_text(encoding="utf-8")

    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="MODIFY",
        target="train.py",
        new_content=current_content,
    )
    result = executor.execute(action)
    assert result.success is False
    assert "no change" in result.error.lower()


def test_execute_rename_actual_filesystem(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="RENAME",
        target="dataset.csv",
        destination="raw_data.csv",
    )
    result = executor.execute(action)
    assert result.success is True
    assert not (test_project / "dataset.csv").exists()
    assert (test_project / "raw_data.csv").exists()
    assert (test_project / "raw_data.csv").read_text(encoding="utf-8").startswith("id,val")


def test_execute_move_actual_filesystem(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="MOVE",
        target="dataset.csv",
        destination="data",
    )
    result = executor.execute(action)
    assert result.success is True
    assert not (test_project / "dataset.csv").exists()
    dest_file = test_project / "data" / "dataset.csv"
    assert dest_file.exists()
    assert "id,val" in dest_file.read_text(encoding="utf-8")


def test_execute_copy_actual_filesystem(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="COPY",
        target="dataset.csv",
        destination="data/backup_data.csv",
    )
    result = executor.execute(action)
    assert result.success is True
    # Both must exist
    assert (test_project / "dataset.csv").exists()
    assert (test_project / "data" / "backup_data.csv").exists()
    assert (test_project / "data" / "backup_data.csv").read_text(encoding="utf-8") == (test_project / "dataset.csv").read_text(encoding="utf-8")


def test_execute_delete_file_and_folder(test_project):
    executor = Executor(project_root=test_project)
    # Delete file
    del_file_action = StructuredAction(operation="DELETE", target="dataset.csv")
    res_f = executor.execute(del_file_action)
    assert res_f.success is True
    assert not (test_project / "dataset.csv").exists()

    # Delete folder
    del_dir_action = StructuredAction(operation="DELETE", target="data")
    res_d = executor.execute(del_dir_action)
    assert res_d.success is True
    assert not (test_project / "data").exists()


def test_execute_safety_blocked_system_path(test_project):
    executor = Executor(project_root=test_project)
    action = StructuredAction(
        operation="DELETE",
        target="C:\\Windows\\System32\\cmd.exe",
    )
    res = executor.execute(action)
    assert res.success is False
    assert "safety guard" in res.error.lower()


def test_full_pipeline_simulation_approval_execution_verification_reindex(test_project):
    """
    End-to-end authoritative pipeline test:
    Simulation -> Approval -> Execution -> Verification -> Re-index
    """
    svc = PreViewAIService(project_root=str(test_project))
    svc.load_project(str(test_project))
    initial_nodes = svc.current_graph.node_count

    # 1. User wants to modify train.py to change threshold
    action = StructuredAction(
        operation="MODIFY",
        target="train.py",
        raw_intent="Change threshold to 0.85",
        target_value="threshold = 0.5",
        new_value="threshold = 0.85",
    )

    # 2. Simulate
    sim = Simulator(svc.current_graph)
    sim_result = sim.simulate(action)
    assert len(sim_result.changes) > 0

    # Store in service state
    svc.last_action = action
    svc.last_sim_result = sim_result

    # 3. Approve and execute
    ok, msg, data = svc.execute_and_verify()
    assert ok is True
    assert "Successfully modified" in msg

    # 4. Verify disk state
    train_disk = test_project / "train.py"
    assert "threshold = 0.85" in train_disk.read_text(encoding="utf-8")

    # 5. Verify verification result
    ver = data["verification"]
    assert ver.status in (VerificationResult.MATCH, VerificationResult.PARTIAL)
    assert len(ver.matches) > 0

    # 6. Verify re-indexed state
    assert svc.current_graph is not None
    assert svc.current_graph.node_count >= initial_nodes
