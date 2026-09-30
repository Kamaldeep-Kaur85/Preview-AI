"""
app/ai/conversation_context.py

Maintains conversational state, reference tracking, and anaphora resolution
across File Explorer locations.

Enables multi-turn workflows:
User: "Where is my resume?"
AI:   "Found: D:\\Documents\\Resume.pdf"
User: "Open its folder."
AI:   "Opening D:\\Documents."
User: "Rename it to Kamaldeep_Resume.pdf."
AI:   "Rename operation prepared..."
User: "Confirm"
AI:   "Done. Renamed..."
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.ai.file_operations import OperationPlan
from app.ai.global_search import SearchResultItem


@dataclass
class ConversationTurn:
    """A single turn in the AI assistant conversation."""
    role: str                       # "user" | "assistant" | "system"
    text: str
    timestamp: float = field(default_factory=time.time)
    referenced_path: Optional[str] = None
    operation_planned: Optional[str] = None


class AIConversationContext:
    """
    Maintains context across File Explorer locations and resolves pronouns/references.
    """

    def __init__(self, navigation_location: Optional[str] = None):
        self.navigation_location: Optional[str] = (
            str(Path(navigation_location).resolve()) if navigation_location else None
        )
        self.ai_scope: str = "Accessible File Explorer locations"
        self.history: List[ConversationTurn] = []

        # Focused file or folder from previous turns
        self.last_target_path: Optional[str] = None
        self.last_search_results: List[SearchResultItem] = []

        # Awaiting user confirmation or clarification
        self.pending_plan: Optional[OperationPlan] = None
        self.pending_clarification: Optional[Dict[str, Any]] = None

    def update_navigation(self, path: str):
        """Update current File Explorer navigation context."""
        try:
            self.navigation_location = str(Path(path).resolve())
        except Exception:
            self.navigation_location = path

    def set_target(self, path: str):
        """Set the active focal target path."""
        try:
            self.last_target_path = str(Path(path).resolve())
        except Exception:
            self.last_target_path = path

    def add_turn(self, role: str, text: str, referenced_path: Optional[str] = None, op: Optional[str] = None):
        """Record a conversation turn."""
        turn = ConversationTurn(
            role=role,
            text=text,
            referenced_path=referenced_path or self.last_target_path,
            operation_planned=op,
        )
        self.history.append(turn)
        if referenced_path:
            self.set_target(referenced_path)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    # ── Pronoun & Reference Resolution ──────────────────────────────────────

    def is_confirmation(self, text: str) -> bool:
        """Check if user text is a confirmation of a pending operation."""
        clean = text.strip().lower()
        confirm_words = {
            "confirm", "yes", "y", "proceed", "ok", "okay", "apply", "do it",
            "confirm delete", "confirm edit", "sure", "approve", "go ahead"
        }
        return clean in confirm_words or clean.startswith("confirm ")

    def is_cancellation(self, text: str) -> bool:
        """Check if user text cancels a pending operation."""
        clean = text.strip().lower()
        cancel_words = {"cancel", "no", "n", "abort", "stop", "nevermind", "dont", "don't"}
        return clean in cancel_words

    def resolve_reference(self, user_text: str) -> Tuple[str, Optional[str]]:
        """
        Resolve anaphoric pronouns and references in user requests.
        Returns (transformed_text, resolved_target_path).
        """
        text = user_text.strip()
        text_lower = text.lower()
        resolved_path = self.last_target_path

        # 1. "open its folder" / "open its directory"
        if re.search(r"\bopen\s+its\s+(?:folder|directory|parent)\b", text_lower):
            if self.last_target_path:
                parent_dir = str(Path(self.last_target_path).parent)
                return f"open {parent_dir}", parent_dir

        # 2. "its folder" / "its directory" / "its parent"
        if "its folder" in text_lower or "its directory" in text_lower or "its parent" in text_lower:
            if self.last_target_path:
                parent_dir = str(Path(self.last_target_path).parent)
                text = re.sub(r"\b(?:its folder|its directory|its parent)\b", lambda m: f'"{parent_dir}"', text, flags=re.IGNORECASE)
                resolved_path = parent_dir
                return text, resolved_path

        # 3. "open it" / "read it" / "show it"
        if re.search(r"\b(?:open|read|show|inspect)\s+it\b", text_lower):
            if self.last_target_path:
                verb = re.findall(r"\b(open|read|show|inspect)\b", text_lower)[0]
                return f"{verb} {self.last_target_path}", self.last_target_path

        # 4. "rename it to <new_name>"
        m = re.search(r"\brename\s+it\s+(?:to|as)\s+(.+)$", text, re.IGNORECASE)
        if m and self.last_target_path:
            new_name = m.group(1).strip().strip("'\"")
            return f"rename {self.last_target_path} to {new_name}", self.last_target_path

        # 5. "move it to <dest>"
        m = re.search(r"\bmove\s+it\s+(?:to|into|in)\s+(.+)$", text, re.IGNORECASE)
        if m and self.last_target_path:
            dest = m.group(1).strip().strip("'\"")
            return f"move {self.last_target_path} to {dest}", self.last_target_path

        # 6. "copy it to <dest>"
        m = re.search(r"\bcopy\s+it\s+(?:to|into|in)\s+(.+)$", text, re.IGNORECASE)
        if m and self.last_target_path:
            dest = m.group(1).strip().strip("'\"")
            return f"copy {self.last_target_path} to {dest}", self.last_target_path

        # 7. "delete it" / "remove it"
        if re.search(r"\b(?:delete|remove|erase)\s+it\b", text_lower):
            if self.last_target_path:
                return f"delete {self.last_target_path}", self.last_target_path

        # 8. "that file" / "this file" / "the file"
        if self.last_target_path and re.search(r"\b(?:that|this|the)\s+file\b", text_lower):
            text = re.sub(r"\b(?:that|this|the)\s+file\b", lambda m: f'"{self.last_target_path}"', text, flags=re.IGNORECASE)
            return text, self.last_target_path

        return text, resolved_path

    # ── Ambiguity Handling ──────────────────────────────────────────────────

    def set_clarification(self, query: str, candidates: List[str], pending_operation: str):
        """Set state when an ambiguous request has multiple candidates."""
        self.pending_clarification = {
            "query": query,
            "candidates": candidates,
            "operation": pending_operation,
        }

    def resolve_clarification(self, user_text: str) -> Optional[str]:
        """
        Check if the user response selects one of the ambiguous candidates.
        Returns the chosen path if resolved, or None.
        """
        if not self.pending_clarification:
            return None

        candidates = self.pending_clarification.get("candidates", [])
        clean = user_text.strip().lower()

        # Check numeric selection (e.g. "1" or "2")
        if clean.isdigit():
            idx = int(clean) - 1
            if 0 <= idx < len(candidates):
                chosen = candidates[idx]
                self.pending_clarification = None
                self.set_target(chosen)
                return chosen

        # Check filename match
        for cand in candidates:
            c_name = Path(cand).name.lower()
            if clean in c_name or clean == c_name or clean in cand.lower():
                self.pending_clarification = None
                self.set_target(cand)
                return cand

        return None
