"""
app/execution/executor.py

Authoritative execution engine: executes validated, approved actions on the real filesystem.
Only runs after explicit user approval and state revalidation.

Guarantees:
- Real filesystem changes (never simulated or faked)
- Real file content modifications (with diff generation & disk read-back verification)
- Syntax validation where applicable (e.g., AST parse for Python)
- Post-operation disk verification before reporting success
- Compatibility with both Action objects and tuple unpacking (exec_ok, exec_msg)
"""
from __future__ import annotations
import ast
import difflib
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.graph.models import StructuredAction
from app.ai.file_operations import FileOperationsEngine, OperationPlan, OperationItem

logger = logging.getLogger("preview_ai.execution")


class ExecutionResult:
    """Result of executing an action on disk."""

    def __init__(
        self,
        action: Optional[StructuredAction] = None,
        success: bool = False,
        message: str = "",
        error: str = "",
        execution_time_ms: float = 0.0,
        diff: Optional[str] = None,
        affected_paths: Optional[List[str]] = None,
    ):
        self.action = action
        self.success = success
        self.message = message
        self.error = error
        self.execution_time_ms = execution_time_ms
        self.diff = diff
        self.affected_paths = affected_paths or []

    def __iter__(self):
        """Allows unpacking as (exec_ok, exec_msg) for backward compatibility."""
        msg = self.message if self.success else (self.error or self.message)
        return iter((self.success, msg))

    def __bool__(self):
        return bool(self.success)

    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict() if self.action else None,
            "success": self.success,
            "message": self.message,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "diff": self.diff,
            "affected_paths": self.affected_paths,
        }


class Executor:
    """
    Executes validated, approved actions on the real filesystem.
    Follows strict safety rules:
    1. Revalidate target before execution
    2. Check system-path protection
    3. Execute real filesystem change
    4. Verify actual change on disk
    5. Return verified success or clear failure
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.file_ops = FileOperationsEngine(current_workspace=str(self.project_root))

    def execute(self, action: StructuredAction) -> ExecutionResult:
        """Execute an approved action with verification."""
        start = time.monotonic()

        # Revalidate: check target exists (except for CREATE)
        if action.operation in ("CREATE", "CREATE_FOLDER"):
            target_path = Path(action.target) if Path(action.target).is_absolute() else (self.project_root / action.target)
        else:
            target_path = self._resolve_target(action.target)
            if not target_path:
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Target not found: {action.target}",
                    execution_time_ms=elapsed,
                )

        # Safety check against OS protected folders
        safe, reason = self.file_ops.validate_path_safety(target_path)
        if not safe:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Blocked by safety guard: {reason}",
                execution_time_ms=elapsed,
            )

        try:
            if action.operation == "DELETE":
                result = self._execute_delete(target_path, action)
            elif action.operation == "MOVE":
                result = self._execute_move(target_path, action)
            elif action.operation == "RENAME":
                result = self._execute_rename(target_path, action)
            elif action.operation == "MODIFY":
                result = self._execute_modify(target_path, action)
            elif action.operation in ("CREATE", "CREATE_FOLDER"):
                result = self._execute_create(target_path, action)
            elif action.operation == "COPY":
                result = self._execute_copy(target_path, action)
            else:
                result = ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Unknown or unsupported operation: {action.operation}",
                )
        except PermissionError as e:
            result = ExecutionResult(
                action=action,
                success=False,
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            logger.exception(f"Execution failed for {action.operation} {action.target}")
            result = ExecutionResult(
                action=action,
                success=False,
                error=f"Execution error: {e}",
            )

        result.execution_time_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"Executed {action.operation} {action.target}: "
            f"{'SUCCESS' if result.success else 'FAILED'} "
            f"({result.execution_time_ms:.1f}ms)"
        )
        return result

    def _execute_delete(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """Delete a file or folder and verify removal."""
        if not target.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Target does not exist to delete: {target}",
            )

        if target.is_file():
            target.unlink()
            if target.exists():
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Verification failed: file still exists at {target}",
                )
            return ExecutionResult(
                action=action,
                success=True,
                message=f"Deleted file: {target.name}",
                affected_paths=[str(target)],
            )
        elif target.is_dir():
            shutil.rmtree(target)
            if target.exists():
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Verification failed: folder still exists at {target}",
                )
            return ExecutionResult(
                action=action,
                success=True,
                message=f"Deleted folder: {target.name}",
                affected_paths=[str(target)],
            )
        else:
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Target is neither file nor directory: {target}",
            )

    def _execute_move(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """Move a file or folder and verify."""
        if not action.destination:
            return ExecutionResult(
                action=action,
                success=False,
                error="No destination specified for MOVE",
            )
        dest = Path(action.destination)
        if not dest.is_absolute():
            dest = self.project_root / dest

        # If dest is existing dir or folder name without extension, place target inside
        if dest.is_dir() or not dest.suffix or str(action.destination).endswith(("/", "\\")):
            dest = dest / target.name

        safe_dest, reason_dest = self.file_ops.validate_path_safety(dest)
        if not safe_dest:
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Destination blocked by safety guard: {reason_dest}",
            )

        # Prevent moving directory into its own child
        if target.is_dir() and dest.resolve().is_relative_to(target.resolve()):
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Cannot move directory into its own subfolder: {dest}",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(dest))

        # Verify on disk
        if not dest.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: moved target not found at {dest}",
            )
        if target.exists() and target.resolve() != dest.resolve():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: source still exists at {target}",
            )

        return ExecutionResult(
            action=action,
            success=True,
            message=f"Moved {target.name} to {dest}",
            affected_paths=[str(target), str(dest)],
        )

    def _execute_rename(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """Rename a file or folder and verify."""
        if not action.destination:
            return ExecutionResult(
                action=action,
                success=False,
                error="No new name specified for RENAME",
            )
        dest = Path(action.destination)
        new_path = dest if dest.is_absolute() else target.parent / dest

        safe_dest, reason_dest = self.file_ops.validate_path_safety(new_path)
        if not safe_dest:
            return ExecutionResult(
                action=action,
                success=False,
                error=f"New name path blocked by safety guard: {reason_dest}",
            )

        new_path.parent.mkdir(parents=True, exist_ok=True)
        target.rename(new_path)

        # Verify on disk
        if not new_path.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: renamed target not found at {new_path}",
            )
        if target.exists() and target.resolve() != new_path.resolve():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: original name still exists at {target}",
            )

        return ExecutionResult(
            action=action,
            success=True,
            message=f"Renamed {target.name} to {action.destination}",
            affected_paths=[str(target), str(new_path)],
        )

    def _execute_modify(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """
        Real file modification:
        1. Read target file.
        2. Determine requested modification and compute diff.
        3. Verify syntax where applicable (e.g. AST parse for Python).
        4. Apply modification to disk.
        5. Verify actual content changed via disk read-back.
        """
        if not target.is_file():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Cannot modify non-file target: {target}",
            )

        if not self.file_ops.is_text_file(target):
            return ExecutionResult(
                action=action,
                success=False,
                error=f"File '{target.name}' is binary or unsupported text format.",
            )

        old_content = target.read_text(encoding="utf-8", errors="replace")
        new_content: Optional[str] = None
        diff_str: Optional[str] = None
        desc: str = ""

        # Check explicit content / new_content on action
        if action.new_content is not None:
            new_content = action.new_content
        elif action.content is not None:
            new_content = action.content
        else:
            # Plan modification using FileOperationsEngine
            try:
                plan = self.file_ops.plan_edit(
                    file_path=str(target),
                    modification_intent=action.raw_intent or f"Modify {target.name}",
                    target_value_or_pattern=action.target_value,
                    new_value=action.new_value,
                )
                if plan.items and plan.items[0].note:
                    new_content = plan.items[0].note
                    diff_str = plan.diff
                    desc = plan.summary
            except Exception as e:
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Failed to plan modification: {e}",
                )

        if new_content is None:
            return ExecutionResult(
                action=action,
                success=False,
                error="Could not determine file modification content.",
            )

        if new_content == old_content:
            return ExecutionResult(
                action=action,
                success=False,
                error="Requested modification produced no change to file content.",
            )

        # Syntax check for Python files
        if target.suffix.lower() == ".py":
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Python syntax verification failed: {e}",
                )

        # Compute diff if not already calculated
        if diff_str is None:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{target.name}",
                tofile=f"b/{target.name}",
                n=3,
            ))
            diff_str = "".join(diff_lines).strip()

        # Write to disk
        target.write_text(new_content, encoding="utf-8")

        # Read back from disk to verify
        read_back = target.read_text(encoding="utf-8", errors="replace")
        if read_back != new_content:
            return ExecutionResult(
                action=action,
                success=False,
                error="Verification failed: file content on disk does not match expected modification.",
            )

        # Verify modified timestamp changed or exists
        if not target.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error="Verification failed: file disappeared after modification.",
            )

        msg = f"Successfully modified {target.name} and verified content on disk."
        if desc:
            msg += f" ({desc})"

        return ExecutionResult(
            action=action,
            success=True,
            message=msg,
            diff=diff_str,
            affected_paths=[str(target)],
        )

    def _execute_create(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """Create a new file or directory on the filesystem and verify."""
        is_dir = (
            action.operation == "CREATE_FOLDER"
            or action.target.endswith(("/", "\\"))
            or target.suffix == ""
        )
        if is_dir:
            target.mkdir(parents=True, exist_ok=True)
            if not target.exists() or not target.is_dir():
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Verification failed: folder not created at {target}",
                )
            return ExecutionResult(
                action=action,
                success=True,
                message=f"Created folder: {target.name}",
                affected_paths=[str(target)],
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            init_content = action.content or action.new_content or ""
            target.write_text(init_content, encoding="utf-8")
            if not target.exists() or not target.is_file():
                return ExecutionResult(
                    action=action,
                    success=False,
                    error=f"Verification failed: file not created at {target}",
                )
            return ExecutionResult(
                action=action,
                success=True,
                message=f"Created file: {target.name}",
                affected_paths=[str(target)],
            )

    def _execute_copy(self, target: Path, action: StructuredAction) -> ExecutionResult:
        """Copy a file or directory and verify."""
        if not action.destination:
            return ExecutionResult(
                action=action,
                success=False,
                error="No destination specified for COPY",
            )
        dest = Path(action.destination)
        if not dest.is_absolute():
            dest = self.project_root / dest

        if dest.is_dir() or not dest.suffix or str(action.destination).endswith(("/", "\\")):
            dest = dest / target.name

        safe_dest, reason_dest = self.file_ops.validate_path_safety(dest)
        if not safe_dest:
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Destination blocked by safety guard: {reason_dest}",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.copytree(str(target), str(dest), dirs_exist_ok=True)
        else:
            shutil.copy2(str(target), str(dest))

        if not dest.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: copied target not found at {dest}",
            )
        if not target.exists():
            return ExecutionResult(
                action=action,
                success=False,
                error=f"Verification failed: source target disappeared during copy: {target}",
            )

        return ExecutionResult(
            action=action,
            success=True,
            message=f"Copied {target.name} to {dest}",
            affected_paths=[str(dest)],
        )

    def _resolve_target(self, target: str) -> Optional[Path]:
        """Resolve target to an actual filesystem path."""
        p = Path(target)
        if p.exists():
            return p.resolve()
        p = self.project_root / target
        if p.exists():
            return p.resolve()
        # Try finding filename within project
        target_name = Path(target).name.lower()
        for root, dirs, files in os.walk(self.project_root):
            for f in files:
                if f.lower() == target_name:
                    return Path(root, f).resolve()
            for d in dirs:
                if d.lower() == target_name:
                    return Path(root, d).resolve()
        return None
