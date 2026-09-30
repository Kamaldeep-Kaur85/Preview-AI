"""
app/ai/intent_parser.py

Intent parser: converts natural-language user requests into StructuredAction.
Supports two modes:
1. Rule-based (offline, no model required) — deterministic pattern matching
2. LLM-assisted (local model) — when a model is available

The rule-based parser handles the MVP use cases reliably.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

from app.graph.models import StructuredAction


class RuleBasedIntentParser:
    """
    Deterministic intent parser using regex patterns.
    Handles operations: DELETE, MOVE, RENAME, MODIFY.
    Supports both explicit destinations and single-target intent simulations,
    folder/file prefixes, quoted paths, and conversational query wrappers.
    Does not require any AI model.
    """

    # Conversational / wrapper prefixes to strip
    PREFIX_PATTERNS = [
        r"^(?:please\s+)?(?:can\s+you\s+|could\s+you\s+|i\s+want\s+to\s+|i\s+would\s+like\s+to\s+|i'd\s+like\s+to\s+|let's\s+|try\s+to\s+)",
        r"^(?:simulate\s+(?:the\s+)?(?:action\s+of\s+)?|what\s+happens\s+if\s+(?:i\s+|we\s+)?|what\s+if\s+(?:i\s+|we\s+)?|is\s+it\s+safe\s+to\s+|how\s+about\s+)",
        r"^(?:can\s+i\s+|should\s+i\s+|what\s+would\s+happen\s+if\s+(?:i\s+|we\s+)?)",
    ]

    def _clean_text(self, raw: str) -> str:
        text = raw.strip()
        # Strip trailing punctuation: ?, !, ., :
        text = re.sub(r"[?!.:;]+$", "", text).strip()
        # Strip leading conversational wrappers
        for prefix in self.PREFIX_PATTERNS:
            text = re.sub(prefix, "", text, flags=re.IGNORECASE).strip()

        # Normalize progressive verbs to imperative
        text = re.sub(r"^(?:deleting|removing)\b", "delete", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:moving)\b", "move", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:renaming)\b", "rename", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:modifying|changing|editing|updating)\b", "modify", text, flags=re.IGNORECASE)
        text = re.sub(r"^(?:creating|adding)\b", "create", text, flags=re.IGNORECASE)
        return text.strip()

    def parse(self, user_text: str) -> Optional[StructuredAction]:
        """Parse user text into a StructuredAction."""
        if not user_text:
            return None
        text = self._clean_text(user_text)
        if not text:
            return None

        # 1. RENAME with explicit destination: 'rename [folder/file] <target> (to|as|into) <dest>'
        m = re.match(
            r"^(?:rename|ren)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+?))\s+(?:to|as|into)\s+(.+)$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            dest = m.group(3).strip().strip("'\"")
            return StructuredAction(
                operation="RENAME",
                target=target,
                destination=dest,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 2. RENAME without explicit destination: 'rename [folder/file] <target>'
        m = re.match(
            r"^(?:rename|ren)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+))$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            p = Path(target)
            dest = f"{p.stem}_renamed{p.suffix}" if p.suffix else f"{p.stem}_renamed"
            return StructuredAction(
                operation="RENAME",
                target=target,
                destination=dest,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 3. MOVE with explicit destination: 'move [folder/file] <target> (to|into|in) <dest>'
        m = re.match(
            r"^(?:move|mv)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+?))\s+(?:to|into|in)\s+(.+)$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            dest = m.group(3).strip().strip("'\"")
            return StructuredAction(
                operation="MOVE",
                target=target,
                destination=dest,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 4. MOVE without explicit destination: 'move [folder/file] <target>'
        m = re.match(
            r"^(?:move|mv)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+))$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            p = Path(target)
            dest = f"archive/{p.name}"
            return StructuredAction(
                operation="MOVE",
                target=target,
                destination=dest,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 5. DELETE: 'delete [folder/file] <target>'
        m = re.match(
            r"^(?:delete|remove|rm|rmdir|del|erase|trash|drop|clean\s*up|destroy|purge|unlink|"
            r"get\s+rid\s+of|throw\s+away)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+))$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            return StructuredAction(
                operation="DELETE",
                target=target,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 6. MODIFY: 'modify [folder/file] <target>'
        m = re.match(
            r"^(?:modify|change|edit|update|alter|rewrite|overwrite|refactor)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+))$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            return StructuredAction(
                operation="MODIFY",
                target=target,
                raw_intent=user_text,
                requires_analysis=True,
            )

        # 7. CREATE: 'create [folder/file] <target>'
        m = re.match(
            r"^(?:create|new|add|touch|mkdir|mkfile|make)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+|directory\s+)?"
            r"""(?:["']([^"']+)["']|(.+))$""",
            text, re.IGNORECASE
        )
        if m:
            target = (m.group(1) or m.group(2)).strip().rstrip("/\\")
            return StructuredAction(
                operation="CREATE",
                target=target,
                raw_intent=user_text,
                requires_analysis=True,
            )

        return None


class IntentParser:
    """
    Main intent parser that uses rule-based parsing by default
    and can optionally use a local LLM for ambiguous requests.
    """

    def __init__(self, model_manager=None):
        self.rule_parser = RuleBasedIntentParser()
        self.model_manager = model_manager

    def parse(self, user_text: str) -> Optional[StructuredAction]:
        """
        Parse user intent. Uses rule-based first, then LLM if available and needed.
        """
        # Try rule-based first (fast, deterministic)
        action = self.rule_parser.parse(user_text)
        if action:
            return action

        # If LLM is available, try LLM parsing for ambiguous input
        if self.model_manager and self.model_manager.is_loaded:
            action = self._llm_parse(user_text)
            if action:
                return action

        return None

    def _llm_parse(self, user_text: str) -> Optional[StructuredAction]:
        """Use the local LLM to parse ambiguous intent."""
        if not self.model_manager:
            return None

        prompt = self._build_intent_prompt(user_text)
        try:
            response = self.model_manager.generate(prompt, max_tokens=200)
            return self._parse_llm_response(response, user_text)
        except Exception:
            return None

    def _build_intent_prompt(self, user_text: str) -> str:
        return f"""You are an intent parser. Convert the user's request into a structured action.

Operations: CREATE, DELETE, MOVE, RENAME, MODIFY
Response format (JSON only):
{{"operation": "CREATE", "target": "new_file.py"}}
{{"operation": "DELETE", "target": "filename.ext"}}
{{"operation": "MOVE", "target": "file.ext", "destination": "new/path/file.ext"}}
{{"operation": "RENAME", "target": "old_name.ext", "destination": "new_name.ext"}}
{{"operation": "MODIFY", "target": "file.ext"}}

User request: "{user_text}"

JSON response:"""

    def _parse_llm_response(self, response: str, raw_intent: str) -> Optional[StructuredAction]:
        """Parse LLM JSON response into StructuredAction."""
        import json
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
            if not json_match:
                return None
            data = json.loads(json_match.group())
            op = data.get("operation", "").upper()
            target = data.get("target", "")
            dest = data.get("destination")
            if op in StructuredAction.VALID_OPERATIONS and target:
                return StructuredAction(
                    operation=op,
                    target=target,
                    destination=dest,
                    raw_intent=raw_intent,
                    requires_analysis=True,
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return None
