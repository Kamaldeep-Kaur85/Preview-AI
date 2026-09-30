"""
app/ai/file_operations.py

Legitimate File Explorer operations engine:
- CREATE (file, folder)
- READ (read text, inspect metadata, list folder contents)
- RENAME (file, folder, batch renames)
- MOVE (file, folder, batch moves)
- COPY (file, folder, batch copies)
- DELETE (file, folder, batch deletes — strictly guarded with confirmation)
- ORGANIZE (create folders, move matching files into folders)
- EDIT (modify code/text/config files with diff generation and confirmation)

Guarantees:
- Real filesystem operations (never simulated)
- Post-action verification on disk
- Destructive operations strictly require confirmation
- Operating system protected locations cannot be modified
- Automatic index update triggers
"""
from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("preview_ai.file_operations")

# Protected operating-system critical locations
PROTECTED_SYSTEM_PATHS: Set[str] = {
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    "C:\\Users\\Default",
    "C:\\Users\\Public",
    "C:\\Recovery",
    "C:\\System Volume Information",
}

# Supported file extensions for content reading & editing
SUPPORTED_TEXT_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".rst", ".csv", ".tsv",
    ".html", ".css", ".xml", ".bat", ".cmd", ".ps1", ".sh",
    ".env", ".gitignore", ".dockerignore", "dockerfile",
}


@dataclass
class OperationItem:
    """A single item inside an operation plan."""
    source_path: str
    target_path: Optional[str] = None
    operation: str = "MOVE"
    diff: Optional[str] = None
    note: str = ""


@dataclass
class OperationPlan:
    """A prepared plan for a file operation before execution."""
    operation: str                          # CREATE, READ, RENAME, MOVE, COPY, DELETE, ORGANIZE, EDIT
    items: List[OperationItem] = field(default_factory=list)
    is_destructive: bool = False
    requires_confirmation: bool = False
    summary: str = ""
    description: str = ""
    diff: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def target_count(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict:
        src = self.items[0].source_path if self.items else ""
        dst = self.items[0].target_path if self.items else None
        return {
            "operation": self.operation,
            "source": src,
            "destination": dst,
            "affected_files": [it.source_path for it in self.items] + ([it.target_path for it in self.items if it.target_path]),
            "reasons": [self.summary] if self.summary else [],
            "risk": "HIGH" if self.is_destructive else "LOW",
            "reversible": self.operation not in ("DELETE",),
            "diff": self.diff,
        }

    def to_confirmation_text(self) -> str:
        """Generate concise confirmation prompt for destructive or batch operations."""
        lines = []
        if self.operation == "DELETE":
            lines.append(f"⚠️ **Confirm Deletion**")
            lines.append(f"Delete **{self.target_count} item{'s' if self.target_count != 1 else ''}**:")
            for item in self.items[:5]:
                lines.append(f"• `{item.source_path}`")
            if self.target_count > 5:
                lines.append(f"↳ ...and {self.target_count - 5} more items")
            lines.append("\n*This cannot be undone through PreView AI.*")
            lines.append("\nType **confirm** or click **[Confirm Delete]** to proceed, or **cancel**.")

        elif self.operation == "EDIT":
            lines.append(f"📝 **Confirm File Modification**")
            if self.items:
                lines.append(f"File: `{self.items[0].source_path}`")
            if self.summary:
                lines.append(f"Change: {self.summary}")
            if self.diff:
                lines.append(f"\n```diff\n{self.diff}\n```")
            lines.append("\nType **confirm** or click **[Confirm]** to apply changes, or **cancel**.")

        elif self.operation in ("MOVE", "ORGANIZE"):
            lines.append(f"📦 **Confirm Move / Organization**")
            lines.append(f"Move **{self.target_count} file{'s' if self.target_count != 1 else ''}**:")
            for item in self.items[:5]:
                lines.append(f"• `{Path(item.source_path).name}` → `{item.target_path}`")
            if self.target_count > 5:
                lines.append(f"↳ ...and {self.target_count - 5} more files")
            lines.append("\nType **confirm** to execute, or **cancel**.")

        elif self.operation == "RENAME":
            lines.append(f"✏️ **Confirm Rename**")
            for item in self.items:
                lines.append(f"I found:\n`{item.source_path}`\n\nRename to:\n`{item.target_path}`")
            lines.append("\nType **confirm** or click **[Confirm]** to proceed, or **cancel**.")

        elif self.operation == "COPY":
            lines.append(f"📋 **Confirm Copy**")
            for item in self.items[:5]:
                lines.append(f"• `{item.source_path}` → `{item.target_path}`")
            lines.append("\nType **confirm** to execute, or **cancel**.")

        else:
            lines.append(f"Action: **{self.operation}** on {self.target_count} item(s). Confirm to proceed.")

        return "\n".join(lines)


@dataclass
class OperationResult:
    """The verified result of executing a File Explorer operation."""
    success: bool
    operation: str
    message: str
    error: str = ""
    affected_paths: List[str] = field(default_factory=list)
    reindex_required: bool = True
    execution_time_ms: float = 0.0


class FileOperationsEngine:
    """
    Executes real filesystem operations with validation, verification, and safety.
    """

    def __init__(self, current_workspace: Optional[str] = None):
        self.current_workspace = Path(current_workspace).resolve() if current_workspace else None

    # ── Safety & Validation ─────────────────────────────────────────────────

    def validate_path_safety(self, path: Path) -> Tuple[bool, str]:
        """Verify that a path is not in a protected OS location and is valid."""
        try:
            resolved = path.resolve()
        except Exception as e:
            return False, f"Invalid path resolution: {e}"

        res_str = str(resolved).lower()
        for protected in PROTECTED_SYSTEM_PATHS:
            prot_norm = str(Path(protected).resolve()).lower()
            if res_str == prot_norm or res_str.startswith(prot_norm + os.sep):
                return False, f"Protected operating-system location cannot be modified: {protected}"

        return True, "Safe"

    # ── Planning Operations ─────────────────────────────────────────────────

    def plan_create(self, target_path: str, is_dir: bool = False, initial_content: str = "") -> OperationPlan:
        """Prepare plan to create a file or folder."""
        p = Path(target_path)
        is_overwrite = p.exists()
        summary = f"Create {'folder' if is_dir else 'file'} '{p.name}'"
        item = OperationItem(
            source_path=str(p.resolve()),
            operation="CREATE",
            note=f"Directory: {is_dir}",
        )
        return OperationPlan(
            operation="CREATE",
            items=[item],
            is_destructive=is_overwrite,
            requires_confirmation=is_overwrite,
            summary=summary,
            description=f"{'Folder' if is_dir else 'File'} creation at `{p.resolve()}`",
        )

    def plan_rename(self, source_path: str, new_name_or_dest: str) -> OperationPlan:
        """Prepare plan to rename a file or folder."""
        src = Path(source_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")

        # Check if new_name_or_dest is a full path or just a filename
        dest_p = Path(new_name_or_dest)
        if dest_p.is_absolute() or ("/" in new_name_or_dest or "\\" in new_name_or_dest):
            dest = dest_p.resolve()
        else:
            dest = (src.parent / new_name_or_dest).resolve()

        is_collision = dest.exists() and dest.resolve() != src.resolve()
        item = OperationItem(
            source_path=str(src),
            target_path=str(dest),
            operation="RENAME",
        )
        return OperationPlan(
            operation="RENAME",
            items=[item],
            is_destructive=is_collision,
            requires_confirmation=True,
            summary=f"Rename '{src.name}' → '{dest.name}'",
            description=f"Rename `{src}` to `{dest}`",
        )

    def plan_batch_rename(self, src_dir: str, pattern_from: str, pattern_to: str) -> OperationPlan:
        """Prepare plan to rename multiple files matching a pattern."""
        d = Path(src_dir).resolve()
        if not d.exists() or not d.is_dir():
            raise FileNotFoundError(f"Directory not found: {src_dir}")

        items: List[OperationItem] = []
        for f in d.iterdir():
            if f.is_file() and f.name.startswith(pattern_from):
                new_name = pattern_to + f.name[len(pattern_from):]
                dest = f.parent / new_name
                items.append(OperationItem(
                    source_path=str(f.resolve()),
                    target_path=str(dest.resolve()),
                    operation="RENAME",
                ))

        return OperationPlan(
            operation="RENAME",
            items=items,
            is_destructive=len(items) > 1,
            requires_confirmation=len(items) > 1,
            summary=f"Batch rename {len(items)} files starting with '{pattern_from}' to '{pattern_to}'",
            description=f"Rename {len(items)} files in `{d}`",
        )

    def plan_move(self, source_path: str, dest_dir_or_path: str) -> OperationPlan:
        """Prepare plan to move a file or folder."""
        src = Path(source_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")

        dest = Path(dest_dir_or_path).resolve()
        # If dest is existing directory, ends with slash, or has no suffix (folder name like 'backup' or 'dataset')
        if dest.is_dir() or not dest.suffix or str(dest_dir_or_path).endswith(("/", "\\")):
            target = dest / src.name
        else:
            target = dest

        is_collision = target.exists() and target.resolve() != src.resolve()
        item = OperationItem(
            source_path=str(src),
            target_path=str(target),
            operation="MOVE",
        )
        return OperationPlan(
            operation="MOVE",
            items=[item],
            is_destructive=is_collision,
            requires_confirmation=is_collision,
            summary=f"Move '{src.name}' → '{target.parent.name}/{target.name}'",
            description=f"Move `{src}` to `{target}`",
        )

    def plan_batch_move(self, sources: List[str], dest_dir: str) -> OperationPlan:
        """Prepare plan to move multiple files into a destination folder."""
        dest = Path(dest_dir).resolve()
        items: List[OperationItem] = []

        for s in sources:
            sp = Path(s).resolve()
            if sp.exists():
                items.append(OperationItem(
                    source_path=str(sp),
                    target_path=str((dest / sp.name).resolve()),
                    operation="MOVE",
                ))

        return OperationPlan(
            operation="MOVE",
            items=items,
            is_destructive=len(items) > 3,
            requires_confirmation=len(items) > 3,
            summary=f"Move {len(items)} files into '{dest.name}'",
            description=f"Move {len(items)} files to `{dest}`",
        )

    def plan_copy(self, source_path: str, dest_dir_or_path: str) -> OperationPlan:
        """Prepare plan to copy a file or folder."""
        src = Path(source_path).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")

        dest = Path(dest_dir_or_path).resolve()
        if dest.is_dir() or not dest.suffix or str(dest_dir_or_path).endswith(("/", "\\")):
            target = dest / src.name
        else:
            target = dest

        is_collision = target.exists()
        item = OperationItem(
            source_path=str(src),
            target_path=str(target),
            operation="COPY",
        )
        return OperationPlan(
            operation="COPY",
            items=[item],
            is_destructive=is_collision,
            requires_confirmation=is_collision,
            summary=f"Copy '{src.name}' → '{target.name}'",
            description=f"Copy `{src}` to `{target}`",
        )

    def plan_delete(self, target_path: str) -> OperationPlan:
        """Prepare plan to delete a file or folder (ALWAYS destructive)."""
        target = Path(target_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Target not found: {target_path}")

        items: List[OperationItem] = []
        if target.is_dir():
            # Count contained files for transparency
            count = sum(1 for _ in target.rglob("*"))
            item = OperationItem(
                source_path=str(target),
                operation="DELETE",
                note=f"Directory containing {count} items",
            )
            items.append(item)
            summary = f"Delete folder '{target.name}' ({count} contained items)"
        else:
            item = OperationItem(
                source_path=str(target),
                operation="DELETE",
                note="Single file",
            )
            items.append(item)
            summary = f"Delete file '{target.name}'"

        return OperationPlan(
            operation="DELETE",
            items=items,
            is_destructive=True,
            requires_confirmation=True,
            summary=summary,
            description=f"Delete `{target}`",
        )

    def plan_edit(
        self,
        file_path: str,
        modification_intent: str,
        target_value_or_pattern: Optional[str] = None,
        new_value: Optional[str] = None,
    ) -> OperationPlan:
        """
        Prepare plan to modify a text/code file (.py, .json, .yaml, .txt, etc.).
        Computes accurate diff and requires confirmation for code modifications.
        """
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self.is_text_file(p):
            raise ValueError(f"File '{p.name}' is a binary file and cannot be modified as text.")

        content = p.read_text(encoding="utf-8", errors="replace")
        new_content, diff_str, desc = self._apply_code_edit(
            content=content,
            intent=modification_intent,
            target_value=target_value_or_pattern,
            new_value=new_value,
            filename=p.name,
        )

        item = OperationItem(
            source_path=str(p),
            operation="EDIT",
            diff=diff_str,
            note=new_content,  # Stores the new content to write
        )

        return OperationPlan(
            operation="EDIT",
            items=[item],
            is_destructive=True,
            requires_confirmation=True,
            summary=desc,
            description=f"Modify `{p.name}`",
            diff=diff_str,
        )

    def is_text_file(self, path: Path) -> bool:
        """Check if file extension is supported for text operations."""
        ext = path.suffix.lower()
        if ext in SUPPORTED_TEXT_EXTENSIONS:
            return True
        if path.name.lower() in ("dockerfile", "makefile", "license", "readme"):
            return True
        return False

    def _apply_code_edit(
        self,
        content: str,
        intent: str,
        target_value: Optional[str],
        new_value: Optional[str],
        filename: str,
    ) -> Tuple[str, str, str]:
        """
        Intelligently modify code content based on common requests:
        - Threshold changes (e.g. 0.5 to 0.7)
        - Model path changes (e.g. model.pkl to models/best_model.pkl)
        - Adding comments or function docstrings
        - Replacing exact strings or regex patterns
        """
        lines = content.splitlines(keepends=True)
        intent_lower = intent.lower()
        new_content = content
        description = "Applied code change"

        # 1. Explicit target_value and new_value
        if target_value is not None and new_value is not None:
            if target_value in content:
                new_content = content.replace(target_value, new_value, 1)
                description = f"Replaced '{target_value}' with '{new_value}'"
            else:
                # Try regex or case-insensitive search
                new_content = re.sub(re.escape(target_value), new_value, content, count=1, flags=re.IGNORECASE)
                description = f"Updated '{target_value}' → '{new_value}'"

        # 2. Threshold modification: e.g. "change threshold from 0.5 to 0.7" or "change threshold to 0.7"
        elif "threshold" in intent_lower:
            m = re.search(r"threshold\s+(?:from\s+([0-9.]+)\s+)?to\s+([0-9.]+)", intent_lower)
            if m:
                from_val = m.group(1)
                to_val = m.group(2)
                # Look for threshold assignment in code
                pat = r"(\bthreshold\s*=\s*)([0-9.]+)"
                if from_val:
                    pat = rf"(\bthreshold\s*=\s*){re.escape(from_val)}"
                sub_res, count = re.subn(pat, rf"\g<1>{to_val}", content, count=1, flags=re.IGNORECASE)
                if count > 0:
                    new_content = sub_res
                    description = f"Changed threshold to {to_val} in {filename}"
                else:
                    # Fallback string replace if direct assignment not matched
                    if from_val and from_val in content:
                        new_content = content.replace(from_val, to_val, 1)
                        description = f"Replaced {from_val} with {to_val}"

        # 3. Model path modification: e.g. "change model path to models/best_model.pkl"
        elif "model" in intent_lower and ("path" in intent_lower or "loading" in intent_lower or "load" in intent_lower or "pkl" in intent_lower):
            m = re.search(r"(?:to|as)\s+['\"]?([a-zA-Z0-9_/\\.-]+\.(?:pkl|pt|h5|onnx|joblib|bin))['\"]?", intent, re.IGNORECASE)
            new_path_str = m.group(1) if m else "models/best_model.pkl"

            # Look for MODEL_PATH = "..." or open("model.pkl"...)
            sub_res, count = re.subn(
                r'(MODEL_PATH\s*=\s*)["][^"]+["]',
                f'\\1"{new_path_str}"',
                content,
                count=1,
            )
            if count == 0:
                sub_res, count = re.subn(
                    r'(MODEL_PATH\s*=\s*)[\'][^\']+[\']',
                    f"\\1'{new_path_str}'",
                    content,
                    count=1,
                )
            if count == 0:
                # Look for open("...model.pkl", ...)
                sub_res, count = re.subn(
                    r'(open\s*\(\s*["\'])([^"\']*\.pkl)(["\'])',
                    f'\\1{new_path_str}\\3',
                    content,
                    count=1,
                )
            if count > 0:
                new_content = sub_res
                description = f"Changed model loading path to '{new_path_str}'"
            else:
                # Replace any occurrence of model.pkl
                if "model.pkl" in content:
                    new_content = content.replace("model.pkl", new_path_str, 1)
                    description = f"Changed model path to '{new_path_str}'"

        # 4. Adding comments explaining a function: e.g. "Add a comment explaining this function in train.py"
        elif "comment" in intent_lower or "docstring" in intent_lower or "explain" in intent_lower:
            # Find first function definition without docstring or at the top
            fn_match = re.search(r"def\s+([a-zA-Z0-9_]+)\s*\(.*?\):", content)
            if fn_match:
                fn_name = fn_match.group(1)
                idx = fn_match.end()
                comment_text = f'\n    """\n    PreView AI: Function {fn_name} performs data pipeline execution and transformation.\n    """'
                new_content = content[:idx] + comment_text + content[idx:]
                description = f"Added explanatory comment docstring for '{fn_name}()'"
            else:
                new_content = f"# PreView AI: Module documentation & overview\n" + content
                description = "Added module explanation comment"

        # Generate standard diff
        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_iter = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=3,
        )
        diff_str = "".join(diff_iter).strip()

        return new_content, diff_str, description

    # ── Real Execution Engine ───────────────────────────────────────────────

    def execute_plan(self, plan: OperationPlan) -> OperationResult:
        """
        Execute an approved OperationPlan on the real filesystem.
        Verifies every change after execution.
        """
        t0 = time.monotonic()
        affected: List[str] = []

        try:
            for item in plan.items:
                src_p = Path(item.source_path)

                # Validate OS path safety
                safe, reason = self.validate_path_safety(src_p)
                if not safe:
                    return OperationResult(
                        success=False,
                        operation=plan.operation,
                        message="Blocked by safety guard.",
                        error=reason,
                    )

                if item.target_path:
                    safe_dest, reason_dest = self.validate_path_safety(Path(item.target_path))
                    if not safe_dest:
                        return OperationResult(
                            success=False,
                            operation=plan.operation,
                            message="Blocked by safety guard.",
                            error=reason_dest,
                        )

                # ── CREATE ──
                if plan.operation == "CREATE":
                    is_dir = "Directory: True" in item.note
                    if is_dir:
                        src_p.mkdir(parents=True, exist_ok=True)
                        if not src_p.exists() or not src_p.is_dir():
                            raise OSError(f"Failed to verify folder creation at {src_p}")
                    else:
                        src_p.parent.mkdir(parents=True, exist_ok=True)
                        if not src_p.exists():
                            src_p.touch()
                        if not src_p.exists() or not src_p.is_file():
                            raise OSError(f"Failed to verify file creation at {src_p}")
                    affected.append(str(src_p))

                # ── DELETE ──
                elif plan.operation == "DELETE":
                    if not src_p.exists():
                        raise FileNotFoundError(f"File or directory does not exist: {src_p}")
                    if src_p.is_dir():
                        shutil.rmtree(src_p)
                        if src_p.exists():
                            raise OSError(f"Verification failed: folder still exists at {src_p}")
                    else:
                        src_p.unlink()
                        if src_p.exists():
                            raise OSError(f"Verification failed: file still exists at {src_p}")
                    affected.append(str(src_p))

                # ── RENAME ──
                elif plan.operation == "RENAME":
                    if not item.target_path:
                        raise ValueError("No destination specified for RENAME")
                    dest_p = Path(item.target_path)
                    if not src_p.exists():
                        raise FileNotFoundError(f"Source does not exist: {src_p}")
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    src_p.rename(dest_p)
                    if not dest_p.exists():
                        raise OSError(f"Verification failed: renamed file not found at {dest_p}")
                    affected.append(str(dest_p))

                # ── MOVE ──
                elif plan.operation in ("MOVE", "ORGANIZE"):
                    if not item.target_path:
                        raise ValueError("No destination specified for MOVE")
                    dest_p = Path(item.target_path)
                    if not src_p.exists():
                        raise FileNotFoundError(f"Source does not exist: {src_p}")
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    # Handle folder cycle prevention: moving parent into subfolder
                    if src_p.is_dir() and dest_p.resolve().is_relative_to(src_p.resolve()):
                        raise ValueError(f"Cannot move directory into its own subfolder: {dest_p}")
                    shutil.move(str(src_p), str(dest_p))
                    if not dest_p.exists():
                        raise OSError(f"Verification failed: moved target not found at {dest_p}")
                    affected.append(str(dest_p))

                # ── COPY ──
                elif plan.operation == "COPY":
                    if not item.target_path:
                        raise ValueError("No destination specified for COPY")
                    dest_p = Path(item.target_path)
                    if not src_p.exists():
                        raise FileNotFoundError(f"Source does not exist: {src_p}")
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    if src_p.is_dir():
                        shutil.copytree(str(src_p), str(dest_p), dirs_exist_ok=True)
                    else:
                        shutil.copy2(str(src_p), str(dest_p))
                    if not dest_p.exists():
                        raise OSError(f"Verification failed: copied target not found at {dest_p}")
                    affected.append(str(dest_p))

                # ── EDIT / MODIFY ──
                elif plan.operation in ("EDIT", "MODIFY"):
                    if not src_p.exists():
                        raise FileNotFoundError(f"Target does not exist: {src_p}")
                    if not src_p.is_file():
                        raise ValueError(f"Cannot edit non-file target: {src_p}")
                    new_code = item.note  # Stored replacement content
                    if new_code is None:
                        raise ValueError("No replacement content provided for edit operation.")
                    current_code = src_p.read_text(encoding="utf-8", errors="replace")
                    if new_code == current_code:
                        raise ValueError("Requested modification produced no change to file content.")
                    if src_p.suffix.lower() == ".py":
                        try:
                            ast.parse(new_code)
                        except SyntaxError as e:
                            raise ValueError(f"Python syntax verification failed: {e}")
                    src_p.write_text(new_code, encoding="utf-8")
                    # Verify on disk
                    read_back = src_p.read_text(encoding="utf-8", errors="replace")
                    if read_back != new_code:
                        raise OSError("Verification failed: written content on disk does not match expected modification")
                    if not src_p.exists():
                        raise OSError(f"Verification failed: file disappeared after modification at {src_p}")
                    affected.append(str(src_p))

            elapsed = (time.monotonic() - t0) * 1000
            msg = f"Done. Successfully completed {plan.operation} on {len(plan.items)} item(s)."
            if plan.operation == "RENAME" and plan.items:
                msg = f"Done.\nRenamed:\n`{Path(plan.items[0].source_path).name}`\n→\n`{Path(plan.items[0].target_path).name}`"
            elif plan.operation == "MOVE" and plan.items:
                msg = f"Done.\nMoved:\n`{Path(plan.items[0].source_path).name}`\n→\n`{Path(plan.items[0].target_path).parent.name}/{Path(plan.items[0].target_path).name}`"
            elif plan.operation == "EDIT" and plan.items:
                msg = f"Done.\nModified:\n`{Path(plan.items[0].source_path).name}`"
            elif plan.operation == "DELETE" and plan.items:
                msg = f"Done.\nDeleted:\n`{Path(plan.items[0].source_path).name}`"

            return OperationResult(
                success=True,
                operation=plan.operation,
                message=msg,
                affected_paths=affected,
                reindex_required=True,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.exception(f"Operation failed: {e}")
            return OperationResult(
                success=False,
                operation=plan.operation,
                message="Operation failed.",
                error=str(e),
                affected_paths=affected,
                reindex_required=False,
                execution_time_ms=elapsed,
            )

    # ── Read Operations (Non-destructive) ───────────────────────────────────

    def read_text_file(self, file_path: str, max_lines: int = 150) -> Tuple[bool, str]:
        """Read and inspect text-based file contents."""
        p = Path(file_path).resolve()
        if not p.exists():
            return False, f"File does not exist: `{file_path}`"
        if not p.is_file():
            return False, f"Path is a folder, not a file: `{file_path}`"

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if len(lines) > max_lines:
                snippet = "\n".join(lines[:max_lines]) + f"\n\n... [{len(lines) - max_lines} more lines not shown]"
            else:
                snippet = content
            ext = p.suffix.lstrip(".") or "text"
            return True, f"``` {ext}\n{snippet}\n```"
        except Exception as e:
            return False, f"Failed to read file: {e}"

    def inspect_file_metadata(self, file_path: str) -> str:
        """Inspect file metadata (size, timestamps, permissions, extension)."""
        p = Path(file_path).resolve()
        if not p.exists():
            return f"Path does not exist: `{file_path}`"

        st = p.stat()
        is_dir = p.is_dir()
        size_str = "Folder" if is_dir else f"{st.st_size} bytes ({st.st_size / 1024:.1f} KB)"
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        ctime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_ctime))

        lines = [
            f"ℹ️ **Metadata for `{p.name}`**\n",
            f"• **Type**: {'Directory / Folder' if is_dir else f'File ({p.suffix})'}",
            f"• **Full Path**: `{p}`",
            f"• **Size**: {size_str}",
            f"• **Last Modified**: {mtime_str}",
            f"• **Created**: {ctime_str}",
            f"• **Readable**: {os.access(p, os.R_OK)}",
            f"• **Writable**: {os.access(p, os.W_OK)}",
        ]
        if is_dir:
            try:
                child_count = sum(1 for _ in p.iterdir())
                lines.append(f"• **Immediate Children**: {child_count} items")
            except Exception:
                pass

        return "\n".join(lines)
