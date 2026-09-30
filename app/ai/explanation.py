"""
app/ai/explanation.py

Explanation engine: generates user-friendly explanations of consequence analysis.
Uses LLM when available, otherwise generates deterministic template-based explanations.
"""
from __future__ import annotations
from typing import List, Optional

from app.graph.models import ConsequenceItem, StructuredAction, ConfidenceLevel, RiskLevel
from app.consequence.analyzer import ConsequenceAnalysis


class ExplanationEngine:
    """
    Generates explanations for consequence analysis results.
    Works without any AI model (template-based).
    Optionally uses local LLM for more natural language.
    """

    def __init__(self, model_manager=None):
        self.model_manager = model_manager

    def explain(self, analysis: ConsequenceAnalysis) -> str:
        """Generate a full explanation of the consequence analysis."""
        if self.model_manager and self.model_manager.is_loaded:
            return self._llm_explain(analysis)
        return self._template_explain(analysis)

    def _template_explain(self, analysis: ConsequenceAnalysis) -> str:
        """Generate a deterministic, template-based explanation."""
        parts = []
        action = analysis.action

        # Header
        parts.append(f"**Impact Analysis: {action.operation} {action.target}**\n")

        # Risk summary
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🔴",
            RiskLevel.BLOCKED: "⛔",
            RiskLevel.UNKNOWN: "❓",
        }
        emoji = risk_emoji.get(analysis.overall_risk, "❓")
        parts.append(f"Overall Risk: {emoji} **{analysis.overall_risk.value}**")
        parts.append(f"Total affected: {analysis.total_affected} | Confirmed edges: {analysis.confirmed_edges}\n")

        # Direct impacts
        if analysis.direct:
            parts.append("**Direct Impact:**")
            for c in analysis.direct:
                parts.append(f"  • {c.description}")

        # Dependency impacts
        if analysis.dependency:
            parts.append("\n**Dependency Impact:**")
            for c in analysis.dependency:
                conf_val = c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence)
                conf_label = f"[{conf_val}]" if conf_val != ConfidenceLevel.CONFIRMED.value else "[CONFIRMED]"
                parts.append(f"  ⚠ {c.description} {conf_label}")
                for ev in c.evidence_chain:
                    parts.append(f"    Evidence: {ev}")

        # Environment dependencies
        if getattr(analysis, "environment", None):
            parts.append("\n**Environment Dependency Impact:**")
            for c in analysis.environment:
                parts.append(f"  ⚠ {c.description} [CONFIRMED]")
                for ev in c.evidence_chain:
                    parts.append(f"    Evidence: {ev}")

        # Secondary impacts
        if analysis.secondary:
            parts.append("\n**Secondary Impact:**")
            for c in analysis.secondary:
                parts.append(f"  ↳ {c.description}")

        # Uncertain impacts
        if analysis.uncertain:
            parts.append("\n**Uncertain:**")
            for c in analysis.uncertain:
                parts.append(f"  ? {c.description}")

        return "\n".join(parts)

    def explain_short(self, analysis: ConsequenceAnalysis) -> str:
        """Generate a short one-line summary."""
        dep_count = len(analysis.dependency or [])
        env_count = len(getattr(analysis, "environment", []) or [])
        if analysis.total_affected == 0:
            return "No impacts detected."
        if dep_count > 0 and env_count > 0:
            return (
                f"{analysis.overall_risk.value} risk: "
                f"{dep_count} project file(s) and {env_count} environment dependency reference(s) detected."
            )
        if env_count > 0:
            return (
                f"{analysis.overall_risk.value} risk: "
                f"{env_count} environment dependency reference(s) detected."
            )
        if dep_count > 0:
            return (
                f"{analysis.overall_risk.value} risk: "
                f"{dep_count} dependency impact{'s' if dep_count > 1 else ''} detected."
            )
        return f"{analysis.overall_risk.value} risk: {analysis.total_affected} item(s) affected."

    def _llm_explain(self, analysis: ConsequenceAnalysis) -> str:
        """Use LLM to generate a natural-language explanation from evidence."""
        evidence_summary = []
        for c in analysis.dependency:
            for ev in c.evidence_chain:
                evidence_summary.append(str(ev))

        prompt = f"""Explain the impact of this action clearly using only the provided evidence.
Do not invent dependencies, facts, or outcomes.

Action: {analysis.action.operation} {analysis.action.target}
Risk: {analysis.overall_risk.value}

Evidence:
{chr(10).join(evidence_summary) if evidence_summary else "No confirmed dependencies found."}

Explain briefly:"""

        try:
            response = self.model_manager.generate(prompt, max_tokens=300)
            # Prepend the template summary and append the LLM explanation
            header = self._template_explain(analysis)
            return f"{header}\n\n**AI Explanation:**\n{response}"
        except Exception:
            return self._template_explain(analysis)
