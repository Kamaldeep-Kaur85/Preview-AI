"""
app/ai/assistant_router.py

Unified File Explorer-Wide AI Assistant:
Integrates:
1. Global Search Engine (4-level layered discovery across File Explorer)
2. File Operations Engine (CREATE, READ, RENAME, MOVE, COPY, DELETE, ORGANIZE, EDIT)
3. Conversation Context Manager (Multi-turn reference resolution & state)
4. Project Intelligence & Consequence Engine (AST dependencies, ONNX impact prediction, Graph)

Maintains:
- Current Navigation Location vs AI Search/Operation Scope
- Confirmation gates for destructive actions
- Automatic re-indexing after every AI modification
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.ai.conversation_context import AIConversationContext
from app.ai.file_operations import FileOperationsEngine, OperationPlan, OperationResult
from app.ai.global_search import GlobalSearchEngine, SearchResultItem

logger = logging.getLogger("preview_ai.assistant")


@dataclass
class AssistantResponse:
    """The unified response from the File Explorer-Wide AI Assistant."""
    reply_text: str
    action_type: str = "ANSWER"             # ANSWER, NAVIGATE, SELECT, PLAN_CONFIRMATION, OPERATION_DONE
    navigation_target: Optional[str] = None # Path to open in File Explorer
    selected_target: Optional[str] = None   # File to select in File Explorer
    pending_plan: Optional[OperationPlan] = None
    affected_paths: List[str] = None
    reindex_summary: Optional[str] = None


class GlobalAIAssistant:
    """
    On-device AI assistant integrated directly into File Explorer.
    Understands, searches, analyzes, and operates on accessible files and folders.
    """

    def __init__(self, service):
        self.service = service
        self.search_engine = GlobalSearchEngine(
            current_nav_path=str(service.project_root) if service.project_root else None,
            cache=service._cache,
        )
        self.operations_engine = FileOperationsEngine(
            current_workspace=str(service.project_root) if service.project_root else None,
        )
        self.context = AIConversationContext(
            navigation_location=str(service.project_root) if service.project_root else None,
        )

    def set_navigation_path(self, path: str):
        """Update current navigation location (without restricting AI scope)."""
        self.search_engine.set_navigation_path(path)
        self.context.update_navigation(path)

    # ── Main message processing entry point ─────────────────────────────────

    def process_message(self, user_text: str) -> AssistantResponse:
        """
        Process any user message through the unified File Explorer AI pipeline.
        """
        raw_query = user_text.strip()
        if not raw_query:
            return AssistantResponse(reply_text="Please enter a question or instruction.")

        query_lower = raw_query.lower()

        # ── 1. Confirmation of pending operation ────────────────────────────
        if self.context.pending_plan:
            if self.context.is_confirmation(raw_query):
                plan = self.context.pending_plan
                self.context.pending_plan = None
                result = self.operations_engine.execute_plan(plan)
                if result.success:
                    # Run post-action verifier on disk
                    from app.verification.verifier import Verifier
                    verifier = Verifier(project_root=self.service.project_root)
                    disk_verified = verifier.verify_paths(result.affected_paths, plan.operation)
                    if not disk_verified:
                        if hasattr(self.service, "_log_event"):
                            self.service._log_event(f"EXECUTION FAILED: {plan.operation} — Disk verification failed", None)
                        return AssistantResponse(
                            reply_text=f"❌ **FAILED**: Execution reported success, but post-operation disk verification failed.",
                            action_type="ANSWER",
                        )
                    reindex_msg = self._reindex_affected_files(result.affected_paths, plan.operation)
                    if hasattr(self.service, "_log_event"):
                        self.service._log_event(f"EXECUTED: {plan.operation} ({len(result.affected_paths)} items) — ✓ Verified", None)
                    reply = f"✓ **Operation Verified & Executed**\n{result.message}\n\n{reindex_msg}" if reindex_msg else f"✓ **Operation Verified & Executed**\n{result.message}"
                    return AssistantResponse(
                        reply_text=reply,
                        action_type="OPERATION_DONE",
                        affected_paths=result.affected_paths,
                        reindex_summary=reindex_msg,
                    )
                else:
                    if hasattr(self.service, "_log_event"):
                        self.service._log_event(f"EXECUTION FAILED: {plan.operation} — {result.error or result.message}", None)
                    return AssistantResponse(
                        reply_text=f"❌ **FAILED**: Could not complete {plan.operation}:\n{result.error or result.message}",
                        action_type="ANSWER",
                    )
            elif self.context.is_cancellation(raw_query):
                plan = self.context.pending_plan
                self.context.pending_plan = None
                if hasattr(self.service, "_log_event"):
                    self.service._log_event(f"CANCELLED: {plan.operation} ({len(plan.items)} items)", None)
                return AssistantResponse(
                    reply_text="Cancelled. No files or folders were modified.",
                    action_type="ANSWER",
                )

        # ── 2. Clarification response resolution ────────────────────────────
        if self.context.pending_clarification:
            chosen = self.context.resolve_clarification(raw_query)
            if chosen:
                op = self.context.pending_clarification.get("operation", "MODIFY")
                self.context.pending_clarification = None
                # Re-dispatch with unambiguous target
                return self.process_message(f"{op.lower()} {chosen}")
            else:
                cands = self.context.pending_clarification.get("candidates", [])
                lines = ["Please specify which file you mean by name or number:"]
                for i, c in enumerate(cands, 1):
                    lines.append(f"{i}. `{c}`")
                return AssistantResponse(reply_text="\n".join(lines))

        # ── 3. Snapdragon hardware diagnostics ──────────────────────────────
        if any(kw in query_lower for kw in ["diagnostic", "hardware", "snapdragon", "npu", "accelerator", "device info"]):
            report = self.service.model_manager.format_diagnostics()
            return AssistantResponse(
                reply_text=f"```text\n{report}\n```",
                action_type="ANSWER",
            )

        # ── 4. Pronoun and reference resolution ─────────────────────────────
        query, resolved_target = self.context.resolve_reference(raw_query)
        q_lower = query.lower()

        # ── 5. Navigation intent: "Open its folder", "Open D:\...", "Go to..."
        nav_match = self._match_navigation_intent(query, resolved_target)
        if nav_match:
            nav_path, is_dir = nav_match
            if is_dir:
                self.set_navigation_path(nav_path)
                # If previous target was a file inside this directory (e.g. 'open its folder'), keep the file as active target
                prev_target = self.context.last_target_path
                if not (prev_target and Path(prev_target).is_file() and str(Path(prev_target).parent.resolve()) == str(Path(nav_path).resolve())):
                    self.context.set_target(nav_path)
                return AssistantResponse(
                    reply_text=f"Opening `{nav_path}`.",
                    action_type="NAVIGATE",
                    navigation_target=nav_path,
                )
            else:
                self.context.set_target(nav_path)
                parent_dir = str(Path(nav_path).parent)
                self.set_navigation_path(parent_dir)
                return AssistantResponse(
                    reply_text=f"Opening `{Path(nav_path).name}`.",
                    action_type="SELECT",
                    navigation_target=parent_dir,
                    selected_target=nav_path,
                )

        # ── 6. Directory inspection: "What is inside D:\Projects?" ───────────
        inside_match = re.search(r"(?:what is inside|what's inside|show contents of|list|inspect folder)\s+['\"]?([a-zA-Z]:[\\/][^'\"]+|[^'\"?]+)", query, re.IGNORECASE)
        if inside_match:
            cand_dir = inside_match.group(1).strip().strip("'\"").rstrip("?. \t\r\n")
            resolved_dir = self._resolve_existing_path(cand_dir)
            if resolved_dir and Path(resolved_dir).is_dir():
                items = self.search_engine.inspect_directory(resolved_dir)
                reply = self.search_engine.format_search_results(f"contents of {Path(resolved_dir).name}", items, location_desc=resolved_dir)
                self.context.set_target(resolved_dir)
                return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # ── 7. Duplicate search: "Find duplicate-looking files" ──────────────
        if "duplicate" in q_lower and "file" in q_lower:
            dups = self.search_engine.find_duplicate_files()
            if not dups:
                return AssistantResponse(reply_text="No duplicate-looking files found across accessible File Explorer locations.")
            lines = [f"Found **{len(dups)} pair{'s' if len(dups) != 1 else ''} of duplicate-looking files** (matching name & size):\n"]
            for i, (f1, f2) in enumerate(dups[:10], 1):
                lines.append(
                    f"{i}. 📄 **{f1.name}** ({f1.formatted_size})\n"
                    f"   • Location A: `{f1.path}`\n"
                    f"   • Location B: `{f2.path}`"
                )
            return AssistantResponse(reply_text="\n".join(lines), action_type="ANSWER")

        # ── 8. Folder category search: "Find folders containing datasets" ───
        folder_cont_match = re.search(r"find\s+folders?\s+containing\s+([a-zA-Z0-9_]+)", q_lower)
        if folder_cont_match:
            kw = folder_cont_match.group(1)
            matching_folders = self.search_engine.find_folders_containing(kw)
            reply = self.search_engine.format_search_results(f"folders containing {kw}", matching_folders)
            return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # ── 9. Code / text content modification: EDIT ───────────────────────
        edit_plan = self._detect_code_modification_intent(query, resolved_target)
        if edit_plan:
            self.context.pending_plan = edit_plan
            return AssistantResponse(
                reply_text=edit_plan.to_confirmation_text(),
                action_type="PLAN_CONFIRMATION",
                pending_plan=edit_plan,
            )

        # ── 10. File Operations: CREATE, RENAME, MOVE, COPY, DELETE, ORGANIZE
        op_plan = self._detect_file_operation_intent(query, resolved_target)
        if op_plan:
            if op_plan.requires_confirmation:
                self.context.pending_plan = op_plan
                return AssistantResponse(
                    reply_text=op_plan.to_confirmation_text(),
                    action_type="PLAN_CONFIRMATION",
                    pending_plan=op_plan,
                )
            else:
                # Safe operation — execute immediately
                res = self.operations_engine.execute_plan(op_plan)
                if res.success:
                    reindex_msg = self._reindex_affected_files(res.affected_paths, op_plan.operation)
                    msg = f"{res.message}\n\n{reindex_msg}" if reindex_msg else res.message
                    return AssistantResponse(reply_text=msg, action_type="OPERATION_DONE", affected_paths=res.affected_paths)
                else:
                    return AssistantResponse(reply_text=f"❌ Operation failed: {res.error}", action_type="ANSWER")

        # ── 11. Read / Inspect file text ────────────────────────────────────
        read_match = re.search(r"^(?:read|open|show|inspect|display)\s+(?:the\s+content\s+of\s+)?['\"]?([^'\"?]+)['\"]?$", query, re.IGNORECASE)
        if read_match and not any(kw in q_lower for kw in ["graph", "dependencies", "impact", "project"]):
            target_cand = read_match.group(1).strip()
            target_p = self._resolve_existing_path(target_cand)
            if target_p and Path(target_p).is_file():
                self.context.set_target(target_p)
                ok, text_content = self.operations_engine.read_text_file(target_p)
                if ok:
                    meta = self.operations_engine.inspect_file_metadata(target_p)
                    return AssistantResponse(
                        reply_text=f"{meta}\n\n**File Content:**\n{text_content}",
                        action_type="SELECT",
                        selected_target=target_p,
                        navigation_target=str(Path(target_p).parent),
                    )

        # ── 12. Global File Search ──────────────────────────────────────────
        search_request = self._match_search_intent(query)
        if search_request:
            q_term, loc, exts, recent = search_request
            results = self.search_engine.search(
                query=q_term,
                explicit_location=loc,
                extensions=exts,
                only_recent=recent,
            )
            self.context.last_search_results = results
            if results:
                self.context.set_target(results[0].path)
            reply = self.search_engine.format_search_results(q_term or "files", results, location_desc=loc)
            return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # ── 13. Project Consequence & Dependency Analysis ───────────────────
        # Hand off to project-level dependency intelligence if within project scope or asking about graph
        return self._handle_project_intelligence(query)

    # ── Intent Matchers & Helpers ───────────────────────────────────────────

    def _match_navigation_intent(self, query: str, default_target: Optional[str]) -> Optional[Tuple[str, bool]]:
        """Check if user wants to open or navigate to a folder or file."""
        q = query.strip()
        q_lower = q.lower()

        # "open its folder"
        if "open its folder" in q_lower or "open its directory" in q_lower:
            if default_target:
                p = Path(default_target)
                target_dir = str(p.parent if p.is_file() else p)
                if Path(target_dir).exists():
                    return target_dir, True

        # "open <path>" or "go to <path>" or "navigate to <path>"
        m = re.match(r"^(?:open|go to|navigate to|cd)\s+['\"]?([a-zA-Z]:[\\/][^'\"]+|[^'\"]+)['\"]?$", q, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            resolved = self._resolve_existing_path(cand)
            if resolved:
                rp = Path(resolved)
                return str(rp), rp.is_dir()

        return None

    def _match_search_intent(self, query: str) -> Optional[Tuple[str, Optional[str], Optional[List[str]], bool]]:
        """
        Extract search parameters: (query_term, location, extensions, only_recent)
        """
        q = query.strip()
        q_lower = q.lower()

        # Detect explicit location: e.g. "in D:\Documents", "in D:\Projects", "in dataset"
        explicit_loc = None
        loc_match = re.search(r"\bin\s+(['\"]?[a-zA-Z]:[\\/][^'\"]+['\"]?|['\"]?[a-zA-Z0-9_-]+[\\/][^'\"]+['\"]?)", query)
        if loc_match:
            cand_loc = loc_match.group(1).strip("'\"")
            resolved_loc = self._resolve_existing_path(cand_loc)
            if resolved_loc and Path(resolved_loc).is_dir():
                explicit_loc = resolved_loc
                # Strip the "in <location>" from query for cleaner term matching
                query = query[:loc_match.start()] + query[loc_match.end():]
                q_lower = query.lower()

        # Recency flag
        only_recent = any(kw in q_lower for kw in ["recent", "recently", "latest", "newest"])

        # Extension detection: "all python files", "all pdf files", "all csv files", etc.
        extensions = None
        if "python" in q_lower or ".py" in q_lower:
            extensions = [".py"]
        elif "pdf" in q_lower or ".pdf" in q_lower:
            extensions = [".pdf"]
        elif "csv" in q_lower or ".csv" in q_lower:
            extensions = [".csv"]
        elif "markdown" in q_lower or ".md" in q_lower:
            extensions = [".md"]
        elif "json" in q_lower or ".json" in q_lower:
            extensions = [".json"]
        elif "model" in q_lower and ("files" in q_lower or "all" in q_lower):
            extensions = [".pkl", ".pt", ".h5", ".onnx", ".joblib"]

        # Search query triggers:
        # "where is <item>?", "where did i save <item>?"
        m = re.search(r"(?:where is|where did i save|where did i put|where's)\s+(?:my\s+)?['\"]?([^'\"?]+)['\"]?", query, re.IGNORECASE)
        if m:
            term = m.group(1).strip()
            return term, explicit_loc, extensions, only_recent

        # "find my <item>", "find <item>", "search for <item>"
        m = re.search(r"(?:find|search\s+for|locate|show\s+me)\s+(?:all\s+)?(?:my\s+)?['\"]?([^'\"?]+)['\"]?", query, re.IGNORECASE)
        if m:
            term = m.group(1).strip()
            # Clean generic words like "files", "python files", "recently"
            clean_term = re.sub(r"\b(?:files?|all|recently|recent|documents?)\b", "", term, flags=re.IGNORECASE).strip()
            if extensions:
                clean_term = re.sub(r"\b(?:python|pdf|csv|markdown|json|model)\b", "", clean_term, flags=re.IGNORECASE).strip()
            return clean_term or "*", explicit_loc, extensions, only_recent

        # Check for direct file extension searches: e.g. "*.csv", "*.pdf"
        if q_lower.startswith("*."):
            return q_lower, explicit_loc, extensions, only_recent

        return None

    def _detect_code_modification_intent(self, query: str, default_target: Optional[str]) -> Optional[OperationPlan]:
        """Detect request to edit or modify code/text files."""
        q_lower = query.lower()
        edit_verbs = ["change", "modify", "update", "edit", "replace", "add comment", "set threshold", "alter"]
        if not any(v in q_lower for v in edit_verbs):
            return None

        # Resolve target file
        target_path = None
        # Look for explicit filename in query: e.g. "in train.py", "in app.py"
        file_match = re.search(r"\bin\s+['\"]?([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+)['\"]?", query, re.IGNORECASE)
        if file_match:
            fname = file_match.group(1)
            target_path = self._resolve_existing_path(fname)
        elif default_target and Path(default_target).is_file():
            target_path = default_target

        if not target_path:
            # Check current project files
            g = self.service.current_graph
            if g:
                for nid, node in g.nodes.items():
                    if node.name.lower() in q_lower and node.is_file:
                        target_path = node.path
                        break

        if not target_path:
            return None

        # Check ambiguity: if query says e.g. "change the model" and multiple model files exist
        if "model" in q_lower and not file_match:
            models = self.search_engine.search("model", extensions=[".pkl", ".pt", ".h5", ".onnx"])
            if len(models) > 1:
                cands = [m.path for m in models]
                self.context.set_clarification(query, cands, "MODIFY")
                return None

        try:
            plan = self.operations_engine.plan_edit(
                file_path=target_path,
                modification_intent=query,
            )
            return plan
        except Exception as e:
            logger.warning(f"Could not plan code edit: {e}")
            return None

    def _detect_file_operation_intent(self, query: str, default_target: Optional[str]) -> Optional[OperationPlan]:
        """Detect and plan file operations: CREATE, RENAME, MOVE, COPY, DELETE, ORGANIZE."""
        q = query.strip()
        q_lower = q.lower()

        # ── CREATE ──
        # e.g. "Create a folder called ML Projects in D:\Projects"
        # e.g. "Create a folder called screenshots"
        # e.g. "Create a README.md in this project"
        create_match = re.search(
            r"^(?:create|make|add)\s+(?:a\s+)?(folder|directory|file)?\s*(?:called|named)?\s*['\"]?([^'\" ]+)['\"]?(?:\s+in\s+['\"]?([^'\"]+)['\"]?)?",
            q, re.IGNORECASE
        )
        if create_match:
            kind = (create_match.group(1) or "").lower()
            name = create_match.group(2).strip()
            loc = (create_match.group(3) or "").strip()

            if name and not any(kw in name.lower() for kw in ["graph", "consequence", "impact"]):
                is_dir = kind in ("folder", "directory") or not Path(name).suffix
                parent_dir = self.service.project_root
                if loc:
                    resolved_loc = self._resolve_existing_path(loc)
                    if resolved_loc:
                        parent_dir = Path(resolved_loc)
                dest_path = str(parent_dir / name)
                return self.operations_engine.plan_create(dest_path, is_dir=is_dir)

        # ── RENAME ──
        # e.g. "Rename train.py to model_training.py"
        # e.g. "Rename all files starting with test_ to start with experiment_"
        batch_ren_match = re.search(
            r"rename\s+all\s+files\s+starting\s+with\s+['\"]?([^'\" ]+)['\"]?\s+to\s+start\s+with\s+['\"]?([^'\" ]+)['\"]?",
            q, re.IGNORECASE
        )
        if batch_ren_match:
            from_pat = batch_ren_match.group(1).strip()
            to_pat = batch_ren_match.group(2).strip()
            src_dir = str(self.service.project_root)
            return self.operations_engine.plan_batch_rename(src_dir, from_pat, to_pat)

        ren_match = re.search(
            r"^(?:rename|ren)\s+(?:file\s+|folder\s+)?['\"]?([^'\" ]+)['\"]?\s+(?:to|as)\s+['\"]?([^'\" ]+)['\"]?$",
            q, re.IGNORECASE
        )
        if ren_match:
            src_name = ren_match.group(1).strip()
            new_name = ren_match.group(2).strip()
            src_path = self._resolve_existing_path(src_name) or default_target
            if src_path:
                return self.operations_engine.plan_rename(src_path, new_name)

        # ── MOVE / ORGANIZE ──
        # e.g. "Move all CSV files into the dataset folder"
        batch_move_match = re.search(
            r"move\s+all\s+([a-zA-Z0-9_.-]+)\s+files\s+(?:in|into|to)\s+(?:the\s+)?['\"]?([^'\"]+)['\"]?",
            q, re.IGNORECASE
        )
        if batch_move_match:
            ext_name = batch_move_match.group(1).lower().lstrip(".")
            dest_dir_name = batch_move_match.group(2).strip().strip("'\"")
            ext = f".{ext_name}"
            # Find matching files in project or current location
            nav_dir = self.service.project_root
            matched_files = [str(f.resolve()) for f in nav_dir.glob(f"*{ext}")]
            dest_path = str(nav_dir / dest_dir_name)
            return self.operations_engine.plan_batch_move(matched_files, dest_path)

        # Single MOVE: e.g. "Move heart.csv into the dataset folder"
        move_match = re.search(
            r"^(?:move|mv)\s+['\"]?([^'\" ]+)['\"]?\s+(?:to|into|in)\s+(?:the\s+)?['\"]?([^'\"]+)['\"]?$",
            q, re.IGNORECASE
        )
        if move_match:
            src_name = move_match.group(1).strip()
            dest_name = move_match.group(2).strip().strip("'\"")
            src_path = self._resolve_existing_path(src_name) or default_target
            if src_path:
                dest_dir = self._resolve_existing_path(dest_name) or str(Path(src_path).parent / dest_name)
                return self.operations_engine.plan_move(src_path, dest_dir)

        # ── COPY ──
        # e.g. "Copy requirements.txt to D:\backup"
        copy_match = re.search(
            r"^(?:copy|cp)\s+['\"]?([^'\" ]+)['\"]?\s+(?:to|into|in)\s+['\"]?([^'\"]+)['\"]?$",
            q, re.IGNORECASE
        )
        if copy_match:
            src_name = copy_match.group(1).strip()
            dest_name = copy_match.group(2).strip().strip("'\"")
            src_path = self._resolve_existing_path(src_name) or default_target
            if src_path:
                dest_dir = self._resolve_existing_path(dest_name) or str(Path(src_path).parent / dest_name)
                return self.operations_engine.plan_copy(src_path, dest_dir)

        # ── DELETE ──
        # e.g. "Delete screenshots" or "Delete heart.csv"
        # Only treat as real deletion if explicit delete command rather than "what if I delete" simulation!
        sim_words = ["what happens", "what if", "consequence", "impact", "simulate", "can i", "is it safe"]
        is_simulation = any(sw in q_lower for sw in sim_words)

        if not is_simulation:
            del_match = re.search(
                r"^(?:delete|remove|rm|del|erase|trash)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+)?['\"]?([^'\"?]+)['\"]?$",
                q, re.IGNORECASE
            )
            if del_match:
                target_name = del_match.group(1).strip()
                # Check ambiguity: "delete the old one"
                if "old" in target_name.lower():
                    # Find candidates
                    cands = [item.path for item in self.context.last_search_results]
                    if len(cands) > 1:
                        self.context.set_clarification(q, cands, "DELETE")
                        return None

                target_path = self._resolve_existing_path(target_name) or default_target
                if target_path:
                    return self.operations_engine.plan_delete(target_path)

        return None

    def _resolve_existing_path(self, candidate_name: str) -> Optional[str]:
        """Resolve a candidate name or path to an actual existing filesystem path."""
        if not candidate_name:
            return None
        clean_name = candidate_name.strip().strip("'\"").rstrip("?. \t\r\n")
        try:
            p = Path(clean_name)
            if p.exists():
                return str(p.resolve())
        except Exception:
            pass

        # Check relative to navigation path
        if self.service.project_root:
            try:
                cand = self.service.project_root / clean_name
                if cand.exists():
                    return str(cand.resolve())
            except Exception:
                pass

        # Check in graph nodes
        g = self.service.current_graph
        if g:
            node = g.find_node_by_name(clean_name)
            if node and Path(node.path).exists():
                return str(Path(node.path).resolve())

        # Check in cache / search
        cached = self.search_engine.search(clean_name, max_results=1)
        if cached:
            return cached[0].path

        return None

    def _reindex_affected_files(self, affected_paths: List[str], operation: str) -> str:
        """
        Automatically update project state graph and cache after any AI modification.
        """
        if not affected_paths:
            return ""

        g = self.service.current_graph
        gb = self.service.graph_builder
        reindexed_count = 0

        for p_str in affected_paths:
            p = Path(p_str)
            # Update cache
            if self.service._cache:
                try:
                    if operation == "DELETE":
                        self.service._cache.delete_file(p_str)
                    elif p.exists():
                        st = p.stat()
                        self.service._cache.upsert_file(
                            path=str(p.resolve()),
                            name=p.name,
                            node_type="FOLDER" if p.is_dir() else "FILE",
                            size_bytes=st.st_size if p.is_file() else 0,
                            mtime=st.st_mtime,
                            extension=p.suffix.lower(),
                            analysis_done=True,
                        )
                except Exception as e:
                    logger.debug(f"Cache update failed: {e}")

            # Update project graph if inside project
            if g and gb and self.service.project_root:
                try:
                    if p.resolve() == self.service.project_root or self.service.project_root in p.resolve().parents:
                        ev_type = "DELETE" if operation == "DELETE" else "MODIFY"
                        with self.service._graph_lock:
                            self.service.current_graph, _ = gb.incremental_update_file(g, p, ev_type)
                        reindexed_count += 1
                except Exception as e:
                    logger.debug(f"Incremental graph update failed: {e}")

        node_cnt = self.service.current_graph.node_count if self.service.current_graph else 0
        edge_cnt = self.service.current_graph.edge_count if self.service.current_graph else 0

        return f"Updated project index:\n{node_cnt} files\n{edge_cnt} relationships"

    def _handle_project_intelligence(self, query: str) -> AssistantResponse:
        """
        Fall back to project dependency, simulation, and consequence analysis.
        """
        g = self.service.current_graph
        if not g:
            return AssistantResponse(
                reply_text=(
                    f"I am monitoring File Explorer at `{self.service.project_root}`.\n\n"
                    "You can ask me to search files, open folders, create or edit code, "
                    "or click **⚡ Index as Project** to inspect code dependencies!"
                ),
                action_type="ANSWER",
            )

        q_lower = query.lower()

        # Check simulation intent: "what happens if I delete...", "what happens if I move..."
        sim_words = ["what happens", "what if", "consequence", "impact", "simulate", "can i delete", "safe to delete", "break"]
        if any(sw in q_lower for sw in sim_words):
            ok, msg, data = self.service.simulate_intent(query)
            if not ok and self.context.last_target_path:
                target_name = Path(self.context.last_target_path).name
                op = "delete" if "delete" in q_lower else ("modify" if "modify" in q_lower else "delete")
                ok, msg, data = self.service.simulate_intent(f"{op} {target_name}")

            if ok and "impact" in data:
                impact = data["impact"]
                expl = data.get("explanation", "")
                r_text = impact.risk.value
                reply = (
                    f"⚡ **Consequence Analysis: {impact.operation} `{impact.changed_object}`**\n"
                    f"Risk Level: **{r_text}**\n\n"
                    f"{expl}\n\n"
                    f"{impact.summary}"
                )
                return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # Check "Why does X depend on Y?"
        why_match = re.search(r"why\s+does\s+([a-zA-Z0-9_.-]+)\s+depend\s+on\s+([a-zA-Z0-9_.-]+)", q_lower)
        if why_match:
            src_name = why_match.group(1).lower()
            tgt_name = why_match.group(2).lower()
            matching_edges = [
                e for e in g.edges
                if (src_name in e.source_id.lower() or Path(e.source_id).name.lower() == src_name)
                and (tgt_name in e.target_id.lower() or Path(e.target_id).name.lower() == tgt_name)
            ]
            if matching_edges:
                edge = matching_edges[0]
                ev_lines = []
                for ev in edge.evidence:
                    loc = f"line {ev.line_number}: " if ev.line_number else ""
                    raw = f"`{ev.raw_text}`" if ev.raw_text else f"{ev.method}"
                    ev_lines.append(f"• At {loc}{raw} [{ev.confidence.value}]")
                ev_desc = "\n".join(ev_lines)
                reply = (
                    f"**{why_match.group(1)}** depends on **{why_match.group(2)}** via `{edge.edge_type.value}` relationship.\n\n"
                    f"**Verified Evidence:**\n{ev_desc}\n\n"
                    f"If `{why_match.group(2)}` is altered or removed, `{why_match.group(1)}` will directly break."
                )
                return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # Check "What does <file> do?" / Role explanation
        role_match = re.search(r"(?:what does|explain|what is the role of)\s+([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+)", q_lower)
        if role_match:
            target_f = role_match.group(1)
            node = g.find_node_by_name(target_f)
            if node:
                incoming = g.get_dependents(node.node_id)
                outgoing = [e for e in g.edges if e.source_id == node.node_id]
                desc = f"**{node.name}** is a project component monitored by PreView AI."
                if node.name.endswith(".py"):
                    desc = f"**{node.name}** is a Python script containing logic, utilities, or training code."
                elif node.name.endswith(".csv"):
                    desc = f"**{node.name}** is a tabular dataset file."
                elif node.name.endswith(".pkl"):
                    desc = f"**{node.name}** is a serialized machine learning model or preprocessing artifact."

                lines = [desc]
                if incoming:
                    lines.append(f"\n🔗 **Required by ({len(incoming)} files)**: {', '.join(f'`{d.name}`' for _, d in incoming[:3])}")
                if outgoing:
                    lines.append(f"\n➡️ **References ({len(outgoing)} files)**: {', '.join(f'`{Path(e.target_id).name}`' for e in outgoing[:3])}")
                return AssistantResponse(reply_text="\n".join(lines), action_type="ANSWER")

        # Check "Where is the configuration for this project?"
        if any(kw in q_lower for kw in ["where is config", "where is the config", "configuration", "config file", "where are settings"]):
            config_nodes = [
                n for n in g.nodes.values()
                if n.name.lower().endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"))
                or "config" in n.name.lower() or "setting" in n.name.lower()
            ]
            if config_nodes:
                lines = [f"Found **{len(config_nodes)} configuration file{'s' if len(config_nodes) != 1 else ''}** in this project:\n"]
                for cn in config_nodes:
                    lines.append(f"• 📄 **{cn.name}** (`{cn.path}`)")
                return AssistantResponse(reply_text="\n".join(lines), action_type="ANSWER")
            else:
                return AssistantResponse(reply_text="No configuration files (JSON, YAML, TOML, .env) were detected in the indexed project.", action_type="ANSWER")

        # Check "What uses <file>?" / dependencies
        if any(kw in q_lower for kw in ["what uses", "who uses", "depend", "dependencies", "who imports", "which files depend"]):
            # Find target
            matched_nodes = []
            for nid, node in g.nodes.items():
                if node.name.lower() in q_lower or Path(nid).name.lower() in q_lower:
                    matched_nodes.append((nid, node))
            matched_nodes.sort(key=lambda x: len(x[1].name), reverse=True)
            if matched_nodes:
                nid, node = matched_nodes[0]
                deps = g.get_dependents(nid)
                if deps:
                    lines = [f"Found **{len(deps)} verified dependent{'s' if len(deps) != 1 else ''}** for `{node.name}`:\n"]
                    for edge, dep_node in deps:
                        ev_summary = "detected code reference"
                        ev_line = ""
                        ev_conf = "High"
                        if edge.evidence:
                            ev = edge.evidence[0]
                            ev_summary = ev.raw_text or ev.method or f"{edge.edge_type.value} reference"
                            ev_line = f" (line {ev.line_number})" if ev.line_number else ""
                            ev_conf = ev.confidence.value.title() if hasattr(ev.confidence, "value") else str(ev.confidence).title()
                        
                        why_desc = f"{edge.edge_type.value.lower()} `{node.name}`"
                        if edge.edge_type.value == "LOADS":
                            why_desc = f"loads `{node.name}` model directly into memory"
                        elif edge.edge_type.value == "READS":
                            why_desc = f"reads `{node.name}` dataset for processing"
                        elif edge.edge_type.value == "IMPORTS":
                            why_desc = f"imports `{node.name}` module"

                        lines.append(
                            f"**FILE**\n"
                            f"→ `{dep_node.path}`\n\n"
                            f"**WHY**\n"
                            f"→ {why_desc}\n\n"
                            f"**SOURCE**\n"
                            f"→ {ev_summary}{ev_line}\n\n"
                            f"**Confidence**:\n"
                            f"{ev_conf}\n"
                            f"---"
                        )
                    return AssistantResponse(reply_text="\n".join(lines), action_type="ANSWER")
                else:
                    return AssistantResponse(
                        reply_text=f"I couldn't determine a reliable dependency for **{node.name}**. It has no detected incoming dependents in the project.",
                        action_type="ANSWER",
                    )

        # Overview / architecture
        if any(kw in q_lower for kw in ["what is this project", "overview", "explain project", "explain this project", "architecture", "what does this project do"]):
            stats = self.service.get_graph_stats()
            reply = (
                f"📦 **Project Architecture Overview: {self.service.project_root.name}**\n\n"
                f"Contains **{stats['nodes']} files** connected by **{stats['edges']} verified relationships**.\n"
                "You can select any file or ask questions like *'What happens if I delete dataset.csv?'*, *'Where is the configuration for this project?'*, or *'What uses dataset.csv?'*."
            )
            return AssistantResponse(reply_text=reply, action_type="ANSWER")

        # General friendly fallback
        return AssistantResponse(
            reply_text=(
                f"PreView AI is active across your File Explorer (current context: `{self.service.project_root.name}`).\n\n"
                "You can:\n"
                "• **Search anywhere**: *'Where is my resume?'*, *'Find all PDF files in D:\\Documents'*\n"
                "• **Operate on files**: *'Rename train.py to model_training.py'*, *'Move heart.csv to dataset'*,\n"
                "• **Edit code safely**: *'Change threshold to 0.7 in train.py'*\n"
                "• **Simulate consequences**: *'What happens if I delete heart.csv?'*"
            ),
            action_type="ANSWER",
        )
