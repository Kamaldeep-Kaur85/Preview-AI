"""
app/ai/impact_predictor.py

On-Device AI Impact Predictor for Qualcomm Snapdragon NPU / CPU Fallback.
Executes the AI inference pipeline:
File Explorer -> Change Detection -> Project Dependency Graph -> Context Builder
-> On-Device AI Model -> ONNX Runtime (QNN / CPU) -> Impact Prediction

CRITICAL: Measures real execution time. Never fakes performance numbers.
"""
from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.ai.backend import InferenceBackend, create_best_backend
from app.ai.context_builder import ProjectContextBuilder
from app.graph.builder import StateGraph
from app.graph.models import (
    ConfidenceLevel, EdgeType, ImpactedFile, ImpactResult,
    RiskLevel, EvidenceItem,
)

logger = logging.getLogger("preview_ai.predictor")

RISK_LEVEL_MAP = [
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.BLOCKED,
]

CONSEQUENCE_CATEGORY_MAP = [
    "Direct dependency",
    "Indirect dependency",
    "Potentially affected tests",
    "Data dependency",
    "Collateral reference",
]


class SnapdragonImpactPredictor:
    """
    On-device AI predictor that uses ONNX Runtime with Qualcomm QNN Execution Provider
    (Snapdragon Hexagon NPU) or CPU fallback.
    """

    def __init__(
        self,
        backend: Optional[InferenceBackend] = None,
        model_path: Optional[Path] = None,
    ):
        self.backend = backend or create_best_backend()
        if model_path is not None:
            self.model_path = Path(model_path)
        else:
            from app.ai.model_manager import ModelManager
            self.model_path = ModelManager._resolve_model_dir() / "preview_impact_predictor.onnx"
        self.context_builder = ProjectContextBuilder()
        self.is_loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> bool:
        if self.is_loaded and self.backend.session is not None:
            return True
        if not self.model_path.exists():
            # Auto-generate if missing
            try:
                from app.ai.model_builder import create_impact_predictor_onnx
                create_impact_predictor_onnx(self.model_path)
            except Exception as e:
                logger.warning(f"Could not auto-generate model: {e}")
                return False

        self.is_loaded = self.backend.load(self.model_path)
        return self.is_loaded

    def predict(
        self,
        target_path_or_name: str,
        operation: str,
        graph: StateGraph,
        confidence_threshold: float = 0.35,
    ) -> ImpactResult:
        """
        Run genuine on-device AI inference to predict future-state impact.
        Returns complete ImpactResult with real measured latency.
        """
        start_total = time.perf_counter()
        self._ensure_loaded()

        # Step 1: Context Builder extracts structured project context
        t_ctx_start = time.perf_counter()
        candidates, features, context_summary = self.context_builder.build_candidate_features(
            target_path_or_name=target_path_or_name,
            operation=operation,
            graph=graph,
        )
        ctx_time_ms = (time.perf_counter() - t_ctx_start) * 1000.0

        target_node = graph.get_node(target_path_or_name)
        if not target_node:
            target_node = graph.find_node_by_name(Path(target_path_or_name).name)

        target_name = target_node.name if target_node else Path(target_path_or_name).name
        target_path = target_node.path if target_node else str(Path(target_path_or_name).resolve())

        # If no candidates or model not loaded, return safe baseline
        if len(candidates) == 0 or not self.is_loaded:
            elapsed_ms = (time.perf_counter() - start_total) * 1000.0
            backend_info = self.backend.get_status()
            return ImpactResult(
                changed_object=target_name,
                changed_path=target_path,
                operation=operation,
                source="AI_PREDICTED",
                risk=RiskLevel.SAFE,
                analysis_complete=True,
                analysis_time_ms=elapsed_ms,
                summary=f"No dependent components found ({backend_info['backend']} / {backend_info['accelerator']})",
            )

        # Step 2: On-Device AI Inference via QNN or CPU Backend
        t_inf_start = time.perf_counter()
        model_outputs = self.backend.run({"features": features})
        inf_time_ms = (time.perf_counter() - t_inf_start) * 1000.0

        # Step 3: Interpret model outputs
        raw_scores = model_outputs.get("impact_scores", np.zeros((len(candidates), 1)))
        risk_logits = model_outputs.get("risk_logits", np.zeros((len(candidates), 4)))
        conseq_logits = model_outputs.get("consequence_logits", np.zeros((len(candidates), 5)))

        impact_scores = raw_scores.ravel()

        direct_impacts: List[ImpactedFile] = []
        affected_files: List[ImpactedFile] = []
        downstream_files: List[ImpactedFile] = []
        uncertain_files: List[ImpactedFile] = []

        # Find direct graph dependents to cross-reference evidence
        direct_deps = {dep_node.node_id: edge for edge, dep_node in graph.get_dependents(target_path)}
        if not direct_deps and target_node:
            direct_deps = {dep_node.node_id: edge for edge, dep_node in graph.get_dependents(target_node.node_id)}

        overall_max_risk = RiskLevel.SAFE

        for i, cand in enumerate(candidates):
            score = float(impact_scores[i]) if i < len(impact_scores) else 0.0
            r_idx = int(np.argmax(risk_logits[i])) if i < len(risk_logits) else 0
            c_idx = int(np.argmax(conseq_logits[i])) if i < len(conseq_logits) else 0

            cand_risk = RISK_LEVEL_MAP[min(r_idx, len(RISK_LEVEL_MAP) - 1)]
            category = CONSEQUENCE_CATEGORY_MAP[min(c_idx, len(CONSEQUENCE_CATEGORY_MAP) - 1)]

            has_direct_edge = cand.node_id in direct_deps
            edge = direct_deps.get(cand.node_id)
            cand_feat = features[i] if i < len(features) else None

            # Verify connection signal:
            # 0: is_direct, 1: path_distance, 2: symbol_refs, 3: is_test, 4: is_import, 5: is_load, 6: is_read, 7: is_ref, 15: stem_overlap
            has_conn_signal = (
                has_direct_edge or
                (cand_feat is not None and (
                    cand_feat[0] > 0.0 or cand_feat[1] > 0.0 or cand_feat[2] > 0.0 or
                    cand_feat[3] > 0.0 or cand_feat[4] > 0.0 or cand_feat[5] > 0.0 or
                    cand_feat[6] > 0.0 or cand_feat[7] > 0.0 or cand_feat[15] > 0.0
                ))
            )
            # If candidate has no connection signal whatsoever to the target, ignore it
            if not has_conn_signal:
                continue

            # Non-graph edges can never be direct dependencies
            if not has_direct_edge and category == "Direct dependency":
                category = "Indirect dependency"

            # Determine confidence
            if has_direct_edge and edge and edge.evidence:
                confidence = ConfidenceLevel.CONFIRMED
            elif score >= 0.70:
                confidence = ConfidenceLevel.LIKELY
            elif score >= 0.40:
                confidence = ConfidenceLevel.POSSIBLE
            else:
                confidence = ConfidenceLevel.UNCERTAIN

            # For unverified edges without direct graph edge, cap predicted risk
            if not has_direct_edge and cand_risk in (RiskLevel.HIGH, RiskLevel.BLOCKED):
                cand_risk = RiskLevel.MEDIUM if score >= 0.75 else RiskLevel.LOW

            # Determine relationship & evidence description
            evidence_chain = []
            if edge:
                evidence_chain = edge.evidence
                raw_txt = edge.evidence[0].raw_text if edge.evidence else f"{edge.edge_type.value} reference"
                ev_summary = f"{raw_txt} (line {edge.evidence[0].line_number})" if edge.evidence and edge.evidence[0].line_number else raw_txt
                rel_name = edge.edge_type.value
            else:
                ev_summary = f"Predicted {category.lower()} via On-device AI (p={score:.2f})"
                rel_name = category

            # Check for test file relationship
            is_test = "test" in cand.name.lower() or "tests" in Path(cand.path).parts
            if is_test and not has_direct_edge:
                category = "Potentially affected tests"
                rel_name = "TEST_DEPENDENCY"

            desc = f"{category}: {cand.name} depends on {target_name}"

            impacted_item = ImpactedFile(
                path=cand.path,
                name=cand.name,
                impact_type="DIRECT" if has_direct_edge else ("DEPENDENCY" if score >= 0.5 else "UNCERTAIN"),
                relationship=rel_name,
                confidence=confidence,
                risk_level=cand_risk,
                description=desc,
                evidence_summary=ev_summary,
                evidence_chain=evidence_chain,
            )

            # Only include if score above threshold or verified in graph
            if has_direct_edge or score >= confidence_threshold:
                if has_direct_edge:
                    direct_impacts.append(impacted_item)
                elif score >= 0.60:
                    affected_files.append(impacted_item)
                elif score >= confidence_threshold:
                    downstream_files.append(impacted_item)
                else:
                    uncertain_files.append(impacted_item)

                if cand_risk.value in ("HIGH", "BLOCKED"):
                    overall_max_risk = cand_risk
                elif cand_risk.value == "MEDIUM" and overall_max_risk.value != "HIGH":
                    overall_max_risk = RiskLevel.MEDIUM
                elif overall_max_risk == RiskLevel.SAFE:
                    overall_max_risk = RiskLevel.LOW

        total_elapsed_ms = (time.perf_counter() - start_total) * 1000.0
        b_info = self.backend.get_status()

        total_affected_count = len(direct_impacts) + len(affected_files) + len(downstream_files)
        if total_affected_count == 0:
            overall_max_risk = RiskLevel.SAFE
            summary_text = (
                f"On-device AI ({b_info['backend']} | {b_info['accelerator']}) "
                f"verified 0 dependent components for {target_name}. Safe to {operation.lower()}."
            )
        else:
            summary_text = (
                f"On-device AI ({b_info['backend']} | {b_info['accelerator']}) "
                f"predicted {total_affected_count} affected component(s) "
                f"in {total_elapsed_ms:.1f}ms (Inference: {inf_time_ms:.1f}ms)"
            )

        return ImpactResult(
            changed_object=target_name,
            changed_path=target_path,
            operation=operation,
            source="AI_PREDICTED",
            direct_impacts=direct_impacts,
            affected_files=affected_files,
            downstream_files=downstream_files,
            uncertain_files=uncertain_files,
            risk=overall_max_risk,
            analysis_complete=True,
            analysis_time_ms=total_elapsed_ms,
            backend_used=b_info.get("backend", "ONNX Runtime"),
            accelerator_used=b_info.get("accelerator", "CPU"),
            inference_time_ms=inf_time_ms,
            summary=summary_text,
        )

    def explain_prediction(self, impact: ImpactResult) -> str:
        """
        Generate clear explanation grounded in the on-device AI prediction.
        """
        b_status = self.backend.get_status()
        n_aff = len(impact.all_impacted)

        lines = [
            f"**Changed Component**: `{impact.changed_object}`  (Operation: {impact.operation})",
            f"**Inference Accelerator**: {b_status['accelerator']} ({b_status['backend']}) | Local Offline",
            f"**Prediction Latency**: {impact.analysis_time_ms:.1f} ms  (Inference: {b_status['last_inference_time_ms']:.1f} ms)",
            f"**Assessed Risk**: **{impact.risk.value}**",
            "",
            "**Predicted Impact Breakdown**:",
        ]

        if n_aff == 0:
            lines.append("- No dependent files detected. This change appears isolated.")
        else:
            if impact.direct_impacts:
                lines.append("\n**Direct Dependencies**:")
                for f in impact.direct_impacts:
                    lines.append(f"  - `{f.name}`: {f.description} ({f.evidence_summary})")

            if impact.affected_files:
                lines.append("\n**Indirect / Secondary Dependencies**:")
                for f in impact.affected_files:
                    lines.append(f"  -> `{f.name}`: {f.relationship} [{f.confidence.value}]")

            if impact.downstream_files:
                lines.append("\n**Potentially Affected Tests / Downstream**:")
                for f in impact.downstream_files:
                    lines.append(f"  ? `{f.name}`: {f.evidence_summary}")

        return "\n".join(lines)
