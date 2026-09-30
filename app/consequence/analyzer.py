"""
app/consequence/analyzer.py

Consequence engine: traces direct, dependency, secondary, and uncertain
impacts from a simulation result. Deterministic — no AI.

Produces ImpactResult which fully answers:
  WHAT CHANGED? WHAT IS AFFECTED? HOW? WHY?
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.graph.models import (
    ConsequenceItem, EvidenceItem, GraphEdge, GraphNode, NodeType,
    RiskLevel, ConfidenceLevel, EdgeType, StructuredAction,
    ImpactResult, ImpactedFile, ChangeEvent, ChangeEventType,
)
from app.graph.builder import StateGraph
from app.simulation.simulator import SimulationResult
from app.consequence.environment_analyzer import EnvironmentDependencyAnalyzer


# ──────────────────────────────────────────────────────────────────────────────
# Legacy ConsequenceAnalysis — kept for backward compat with old CLI mode
# ──────────────────────────────────────────────────────────────────────────────

class ConsequenceAnalysis:
    """Legacy wrapper — prefer ImpactResult for new code."""

    def __init__(
        self,
        action: StructuredAction,
        direct: List[ConsequenceItem],
        dependency: List[ConsequenceItem],
        secondary: List[ConsequenceItem],
        uncertain: List[ConsequenceItem],
        overall_risk: RiskLevel,
        analysis_time_ms: float = 0.0,
        impact_result: Optional[ImpactResult] = None,
        environment: Optional[List[ConsequenceItem]] = None,
    ):
        self.action = action
        self.direct = direct
        self.dependency = dependency
        self.environment = environment or []
        self.secondary = secondary
        self.uncertain = uncertain
        self.overall_risk = overall_risk
        self.analysis_time_ms = analysis_time_ms
        self.impact_result = impact_result  # Canonical result

    @property
    def all_consequences(self) -> List[ConsequenceItem]:
        return self.direct + self.dependency + self.environment + self.secondary + self.uncertain

    @property
    def total_affected(self) -> int:
        return len(self.all_consequences)

    @property
    def confirmed_edges(self) -> int:
        return sum(
            1 for c in self.all_consequences
            if c.confidence == ConfidenceLevel.CONFIRMED
        )

    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict(),
            "direct": [c.to_dict() for c in self.direct],
            "dependency": [c.to_dict() for c in self.dependency],
            "environment": [c.to_dict() for c in self.environment],
            "secondary": [c.to_dict() for c in self.secondary],
            "uncertain": [c.to_dict() for c in self.uncertain],
            "overall_risk": self.overall_risk.value,
            "total_affected": self.total_affected,
            "confirmed_edges": self.confirmed_edges,
            "analysis_time_ms": self.analysis_time_ms,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Main analyzer — produces ImpactResult
# ──────────────────────────────────────────────────────────────────────────────

class ConsequenceAnalyzer:
    """
    Analyzes a simulation result or a filesystem change event
    and produces a structured ImpactResult.

    This is the deterministic core — no AI.
    """

    def __init__(
        self,
        graph: StateGraph,
        env_analyzer: Optional[EnvironmentDependencyAnalyzer] = None,
    ):
        self.graph = graph
        self.env_analyzer = env_analyzer or EnvironmentDependencyAnalyzer()

    # ── Primary entry points ──────────────────────────────────────────────────

    def analyze(self, sim_result: SimulationResult) -> ConsequenceAnalysis:
        """
        Analyze a simulation result (AI-proposed action).
        Returns both legacy ConsequenceAnalysis and embedded ImpactResult.
        """
        start = time.monotonic()
        action = sim_result.action

        impact = self.compute_impact(
            target_name_or_path=action.target,
            operation=action.operation,
            source="AI_PROPOSED",
            destination=action.destination,
        )
        impact.analysis_time_ms = (time.monotonic() - start) * 1000

        # Build legacy ConsequenceAnalysis from ImpactResult
        direct_items = [self._impact_to_consequence(f) for f in impact.direct_impacts]
        dep_items = [self._impact_to_consequence(f) for f in impact.affected_files]
        env_items = [self._impact_to_consequence(f) for f in impact.environment_dependencies]
        sec_items = [self._impact_to_consequence(f) for f in impact.downstream_files]
        unc_items = [self._impact_to_consequence(f) for f in impact.uncertain_files]

        return ConsequenceAnalysis(
            action=action,
            direct=direct_items,
            dependency=dep_items,
            secondary=sec_items,
            uncertain=unc_items,
            overall_risk=impact.risk,
            analysis_time_ms=impact.analysis_time_ms,
            impact_result=impact,
            environment=env_items,
        )

    def analyze_change_event(self, event: ChangeEvent) -> ImpactResult:
        """
        Analyze a real filesystem change event (user-made change).
        Returns ImpactResult directly.
        """
        path = event.path
        op = event.event_type.value
        old_path = event.old_path

        # For renames/moves, analyze the OLD path (it's the one with references)
        if event.event_type in (ChangeEventType.RENAME, ChangeEventType.MOVE) and old_path:
            target = old_path
        else:
            target = path

        impact = self.compute_impact(
            target_name_or_path=target,
            operation=op,
            source="USER_MADE",
            destination=path if event.event_type in (ChangeEventType.RENAME, ChangeEventType.MOVE) else None,
        )
        return impact

    def compute_impact(
        self,
        target_name_or_path: str,
        operation: str,
        source: str = "AI_PROPOSED",
        destination: Optional[str] = None,
    ) -> ImpactResult:
        """
        Core impact computation.
        Resolves the target node, finds all dependents, computes risk.
        """
        # Resolve target
        target_node = self._resolve_target(target_name_or_path)
        changed_name = Path(target_name_or_path).name if target_name_or_path else target_name_or_path
        changed_path = target_node.path if target_node else target_name_or_path

        # Inspect environment dependencies (PATH, PYTHONPATH, JAVA_HOME, ANDROID_HOME, CONDA_*, etc.)
        env_deps = self.env_analyzer.analyze_target(changed_path)
        environment_dependencies = [d.to_impacted_file() for d in env_deps]

        # If target not found in graph
        if not target_node:
            if operation == "CREATE":
                # Creating a new file or folder that is not yet in the index
                direct_impacts = [
                    ImpactedFile(
                        path=changed_path,
                        name=changed_name,
                        impact_type="DIRECT",
                        relationship="DIRECT",
                        confidence=ConfidenceLevel.CONFIRMED,
                        risk_level=RiskLevel.LOW,
                        description=f"{changed_name} will be created as a new project component.",
                        evidence_summary="New file/folder creation.",
                    )
                ]
                # Check if any existing file references this new component
                referencing_files = []
                target_base = changed_name.lower()
                for nid, node in self.graph.nodes.items():
                    for edge in self.graph.edges:
                        if edge.source_id == nid and (target_base in edge.target_id.lower() or target_base in str(edge.evidence).lower()):
                            referencing_files.append(ImpactedFile(
                                path=node.path,
                                name=node.name,
                                impact_type="DEPENDENCY",
                                relationship="SATISFIES_REFERENCE",
                                confidence=ConfidenceLevel.CONFIRMED,
                                risk_level=RiskLevel.LOW,
                                description=f"{node.name} references '{changed_name}'. Creating this component satisfies this dependency.",
                                evidence_summary=f"References {changed_name}",
                            ))
                            break

                risk = RiskLevel.LOW if referencing_files else RiskLevel.NO_CONFIRMED_IMPACT
                summary = (
                    f"Creating '{changed_name}' adds a new component to the project. "
                    + (f"Satisfies references in {len(referencing_files)} file(s)." if referencing_files else "No conflicts detected; safe to proceed.")
                )
                return ImpactResult(
                    changed_object=changed_name,
                    changed_path=changed_path,
                    operation=operation,
                    source=source,
                    destination=destination,
                    direct_impacts=direct_impacts,
                    affected_files=referencing_files,
                    environment_dependencies=environment_dependencies,
                    downstream_files=[],
                    uncertain_files=[],
                    risk=risk,
                    analysis_complete=True,
                    summary=summary,
                )

            # If environment dependencies exist or path exists on disk, synthesize target_node
            try:
                p_disk = Path(changed_path)
                p_exists = p_disk.exists()
                is_dir = p_disk.is_dir() if p_exists else ("." not in changed_name)
            except Exception:
                p_disk = None
                p_exists = False
                is_dir = "." not in changed_name

            if environment_dependencies or p_exists:
                target_node = GraphNode(
                    node_id=str(p_disk) if p_disk else changed_path,
                    name=changed_name,
                    path=str(p_disk) if p_disk else changed_path,
                    node_type=NodeType.FOLDER if is_dir else NodeType.FILE,
                    exists=p_exists,
                )
            else:
                target_name_lower = changed_name.lower()
                is_cache_or_config = (
                    target_name_lower.startswith(".")
                    or target_name_lower.endswith(("_cache", ".cache"))
                    or target_name_lower in ("cache", ".cache", "tmp", "temp", ".temp", ".tmp", ".gradle", ".android", ".anaconda", ".aws", ".azure", ".ssh", ".kube", "logs", ".logs")
                )
                if is_cache_or_config:
                    return ImpactResult(
                        changed_object=changed_name,
                        changed_path=changed_path,
                        operation=operation,
                        source=source,
                        destination=destination,
                        direct_impacts=[
                            ImpactedFile(
                                path=changed_path,
                                name=changed_name,
                                impact_type="DIRECT",
                                relationship="DIRECT",
                                confidence=ConfidenceLevel.CONFIRMED,
                                risk_level=RiskLevel.LOW,
                                description=f"Configuration/cache item '{changed_name}' will be {self._op_verb(operation)}.",
                                evidence_summary="Config or cache directory with no active environment references.",
                            )
                        ],
                        affected_files=[],
                        environment_dependencies=[],
                        downstream_files=[],
                        uncertain_files=[],
                        risk=RiskLevel.LOW,
                        analysis_complete=True,
                        summary=f"'{changed_name}' is a configuration/cache component with no detected dependencies. Safe to proceed.",
                    )

                unc_file = ImpactedFile(
                    path=changed_path,
                    name=changed_name,
                    impact_type="UNCERTAIN",
                    relationship="UNKNOWN",
                    confidence=ConfidenceLevel.UNCERTAIN,
                    risk_level=RiskLevel.UNKNOWN,
                    description=f"Target '{changed_name}' was not found in the project index.",
                    evidence_summary="File not found in project index; consequence cannot be determined.",
                )
                return ImpactResult(
                    changed_object=changed_name,
                    changed_path=changed_path,
                    operation=operation,
                    source=source,
                    destination=destination,
                    uncertain_files=[unc_file],
                    risk=RiskLevel.UNKNOWN,
                    analysis_complete=False,
                    summary=(
                        f"Target '{changed_name}' was not found in the project index. "
                        f"The project may need to be re-scanned, or the file is outside the monitored scope."
                    ),
                )

        direct_impacts: List[ImpactedFile] = []
        affected_files: List[ImpactedFile] = []
        downstream_files: List[ImpactedFile] = []
        uncertain_files: List[ImpactedFile] = []

        import os

        # Check if target is a folder or directory
        is_folder = (target_node.node_type == NodeType.FOLDER or Path(target_node.path).is_dir())
        folder_descendants: List[GraphNode] = []
        if is_folder:
            folder_norm = os.path.normcase(os.path.abspath(target_node.path))
            for nid, n in self.graph.nodes.items():
                if nid != target_node.node_id:
                    n_norm = os.path.normcase(os.path.abspath(n.path))
                    if n_norm.startswith(folder_norm + os.sep) or n_norm.startswith(folder_norm + "/"):
                        folder_descendants.append(n)

        # Direct impact: the target itself
        target_kind = "Folder" if is_folder else "File"
        if is_folder and folder_descendants:
            if operation == "DELETE":
                folder_detail = f" (contains {len(folder_descendants)} files that will also be deleted)"
            elif operation == "RENAME":
                folder_detail = f" (contains {len(folder_descendants)} files that will also be renamed)"
            elif operation == "MOVE":
                folder_detail = f" (contains {len(folder_descendants)} files that will also be moved)"
            else:
                folder_detail = f" (contains {len(folder_descendants)} files)"
        else:
            folder_detail = ""

        # Determine whether target is an asset/doc folder or non-critical component
        is_asset_or_doc = False
        target_name_lower = target_node.name.lower()
        asset_names = ("screenshots", "screenshot", "images", "img", "docs", "doc", "documentation",
                       "assets", "asset", "figures", "plots", "art", "mockups", "badges")
        asset_exts = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".ico", ".webp", ".md", ".txt")
        critical_exts = (".py", ".pkl", ".pt", ".h5", ".csv", ".tsv", ".parquet", ".json", ".yaml", ".yml", ".toml")

        if any(target_name_lower == a or target_name_lower.startswith(a + "_") or target_name_lower.startswith(a + "-") for a in asset_names):
            is_asset_or_doc = True
        elif not is_folder and target_node.name.lower().endswith(asset_exts):
            is_asset_or_doc = True
        elif is_folder and folder_descendants:
            if all(any(child.name.lower().endswith(ext) for ext in asset_exts) for child in folder_descendants):
                is_asset_or_doc = True

        has_critical_files = any(
            any(n.name.lower().endswith(ext) for ext in critical_exts)
            for n in ([target_node] if not is_folder else folder_descendants)
        )

        if is_asset_or_doc or (is_folder and not folder_descendants and not has_critical_files):
            target_risk = RiskLevel.LOW
        elif operation in ("DELETE", "RENAME", "MOVE") and (has_critical_files or target_node.name.endswith(critical_exts)):
            target_risk = RiskLevel.HIGH
        else:
            target_risk = RiskLevel.MEDIUM

        direct_impacts.append(ImpactedFile(
            path=target_node.path,
            name=target_node.name,
            impact_type="DIRECT",
            relationship="DIRECT",
            confidence=ConfidenceLevel.CONFIRMED,
            risk_level=target_risk,
            description=f"{target_node.name} ({target_kind}) will be {self._op_verb(operation)}{folder_detail}",
            evidence_summary=f"This is the directly changed {target_kind.lower()}.",
        ))

        # Add contained files to direct impacts if folder
        for child in folder_descendants:
            is_child_asset = any(child.name.lower().endswith(ext) for ext in asset_exts)
            if operation == "DELETE":
                child_desc = f"Contained inside {target_node.name}; will be deleted with parent folder"
                child_risk = RiskLevel.LOW if (is_asset_or_doc or is_child_asset) else RiskLevel.HIGH
            elif operation == "RENAME":
                child_desc = f"Contained inside {target_node.name}; path will change when parent folder is renamed"
                child_risk = RiskLevel.LOW if (is_asset_or_doc or is_child_asset) else RiskLevel.HIGH
            elif operation == "MOVE":
                child_desc = f"Contained inside {target_node.name}; path will change when parent folder is moved"
                child_risk = RiskLevel.LOW if (is_asset_or_doc or is_child_asset) else RiskLevel.HIGH
            else:
                child_desc = f"Contained inside {target_node.name}; affected by {operation.lower()}"
                child_risk = RiskLevel.LOW if (is_asset_or_doc or is_child_asset) else RiskLevel.MEDIUM

            direct_impacts.append(ImpactedFile(
                path=child.path,
                name=child.name,
                impact_type="DIRECT",
                relationship="CONTAINS",
                confidence=ConfidenceLevel.CONFIRMED,
                risk_level=child_risk,
                description=child_desc,
                evidence_summary=f"Located in {target_node.name}",
            ))

        # First-order: nodes that DEPEND ON the target or ANY contained file
        nodes_to_check = [target_node] + folder_descendants
        seen: Set[str] = {target_node.node_id}
        for n in folder_descendants:
            seen.add(n.node_id)

        for item_node in nodes_to_check:
            dependents = self.graph.get_dependents(item_node.node_id)
            for edge, dep_node in dependents:
                if dep_node.node_id in seen:
                    continue
                if edge.edge_type == EdgeType.CONTAINS:
                    continue
                seen.add(dep_node.node_id)

                risk = self._assess_edge_risk(edge, operation)
                if is_folder and operation in ("DELETE", "MOVE", "RENAME"):
                    risk = RiskLevel.HIGH
                ev_items = list(edge.evidence)
                ev_summary = self._build_evidence_summary(edge, dep_node, item_node)
                
                if item_node != target_node:
                    op_verb_ing = "Deleting" if operation == "DELETE" else ("Renaming" if operation == "RENAME" else "Moving")
                    desc = f"{dep_node.name} depends on {item_node.name} inside folder '{target_node.name}'. {op_verb_ing} {target_node.name} will break this file."
                else:
                    desc = self._describe_dependency(edge, dep_node, target_node, operation)

                affected_files.append(ImpactedFile(
                    path=dep_node.path,
                    name=dep_node.name,
                    impact_type="DEPENDENCY",
                    relationship=edge.edge_type.value,
                    confidence=ConfidenceLevel.CONFIRMED if is_folder else edge.confidence,
                    risk_level=risk,
                    description=desc,
                    evidence_summary=ev_summary,
                    evidence_chain=ev_items,
                ))

        # Heuristic for dataset folders and data files: check if ML training scripts exist
        is_dataset_target = target_node.name.lower() in ("dataset", "data", "datasets", "raw_data") or target_node.name.endswith((".csv", ".tsv", ".parquet")) or any(
            n.name.endswith((".csv", ".tsv", ".parquet")) for n in folder_descendants
        )
        if is_dataset_target and operation in ("DELETE", "MOVE", "RENAME"):
            for nid, node in self.graph.nodes.items():
                if node.node_id not in seen and node.name.endswith(".py"):
                    if any(k in node.name.lower() for k in ("train", "pipeline", "evaluate", "model", "app")):
                        seen.add(node.node_id)
                        op_word = "Renaming" if operation == "RENAME" else ("Moving" if operation == "MOVE" else "Deleting")
                        op_effect = "renames" if operation == "RENAME" else ("relocates" if operation == "MOVE" else "removes")
                        affected_files.append(ImpactedFile(
                            path=node.path,
                            name=node.name,
                            impact_type="DEPENDENCY",
                            relationship="TRAINING_PIPELINE",
                            confidence=ConfidenceLevel.CONFIRMED,
                            risk_level=RiskLevel.HIGH,
                            description=f"{node.name} is a project script depending on {target_node.name}. {op_word} {target_node.name} {op_effect} data required by this project.",
                            evidence_summary=f"{target_node.name} is the primary dataset component for {node.name}",
                        ))

        # Second+ order: transitive dependents
        for item_node in nodes_to_check:
            all_transitive = self.graph.get_all_affected(item_node.node_id)
            for edge, aff_node, depth in all_transitive:
                if aff_node.node_id in seen:
                    continue
                seen.add(aff_node.node_id)

                ev_items = list(edge.evidence)
                ev_summary = f"Indirectly affected via dependency chain (depth {depth})"

                downstream_files.append(ImpactedFile(
                    path=aff_node.path,
                    name=aff_node.name,
                    impact_type="DOWNSTREAM",
                    relationship=edge.edge_type.value,
                    confidence=ConfidenceLevel.POSSIBLE,
                    risk_level=RiskLevel.MEDIUM,
                    description=f"{aff_node.name} is transitively affected (depth {depth})",
                    evidence_summary=ev_summary,
                    evidence_chain=ev_items,
                ))

        # Determine overall risk considering project code and environment references
        risk = self._compute_overall_risk_with_env(
            operation=operation,
            target_node=target_node,
            affected=affected_files,
            environment=environment_dependencies,
            downstream=downstream_files,
            uncertain=uncertain_files,
            is_folder=is_folder,
            folder_descendants=folder_descendants,
            is_asset_or_doc=is_asset_or_doc,
            has_critical_files=has_critical_files,
        )

        # Build summary
        summary = self._build_summary(
            target_node, operation, affected_files, downstream_files, uncertain_files,
            environment=environment_dependencies,
        )

        return ImpactResult(
            changed_object=target_node.name,
            changed_path=target_node.path,
            operation=operation,
            source=source,
            destination=destination,
            direct_impacts=direct_impacts,
            affected_files=affected_files,
            environment_dependencies=environment_dependencies,
            downstream_files=downstream_files,
            uncertain_files=uncertain_files,
            risk=risk,
            analysis_complete=True,
            summary=summary,
        )

    # ── Resolution ────────────────────────────────────────────────────────────

    def _resolve_target(self, target: str) -> Optional[GraphNode]:
        """Resolve target string to graph node using multiple strategies."""
        if not target:
            return None

        # 1. Exact node_id match
        node = self.graph.get_node(target)
        if node:
            return node

        # 2. Absolute path
        try:
            abs_path = Path(target).resolve()
            node = self.graph.get_node(str(abs_path))
            if node:
                return node
        except Exception:
            pass

        # 3. Filename match (case-insensitive)
        node = self.graph.find_node_by_name(Path(target).name)
        if node:
            return node

        # 4. Partial path suffix match
        target_lower = target.lower().replace("\\", "/")
        target_suffix = "/" + target_lower if not target_lower.startswith("/") else target_lower
        for node_id, node in self.graph.nodes.items():
            norm_id = node_id.lower().replace("\\", "/")
            if norm_id.endswith(target_suffix) or norm_id == target_lower:
                return node

        # 5. Stem match (e.g. "dataset" matching "dataset.csv" or "dataset.parquet")
        target_stem = Path(target_lower.strip("/")).name
        for node_id, node in self.graph.nodes.items():
            if Path(node.name).stem.lower() == target_stem:
                return node

        # 6. Check if target exists on disk as a folder within project
        try:
            p = Path(target)
            if not p.is_absolute():
                proj = getattr(self.graph, "project_root", None)
                if proj:
                    cand = Path(proj) / target
                    if cand.exists():
                        p = cand
            if p.exists():
                return GraphNode.from_path(p.resolve())
        except Exception:
            pass

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _op_verb(self, operation: str) -> str:
        verbs = {
            "DELETE": "deleted",
            "MOVE": "moved",
            "RENAME": "renamed",
            "MODIFY": "modified",
            "CREATE": "created",
        }
        return verbs.get(operation.upper(), operation.lower() + "d")

    def _build_evidence_summary(
        self, edge: GraphEdge, dep_node: GraphNode, target_node: GraphNode
    ) -> str:
        verb = self._edge_verb(edge.edge_type.value)
        if edge.evidence:
            ev = edge.evidence[0]
            loc = f" (line {ev.line_number})" if ev.line_number else ""
            return (
                f"{dep_node.name}{loc} {verb} "
                f"{target_node.name} "
                f"[detected via {ev.method}]"
            )
        return f"{dep_node.name} {verb} {target_node.name}"

    def _edge_verb(self, edge_type_value: str) -> str:
        """Return a human-readable present-tense verb for an edge type."""
        verbs = {
            "READS": "reads",
            "IMPORTS": "imports",
            "LOADS": "loads",
            "REFERENCES": "references",
            "CONFIGURES": "configures",
            "DEPENDS_ON": "depends on",
            "EXECUTES": "executes",
            "DECLARES": "declares",
            "LOCATED_IN": "is located in",
        }
        return verbs.get(edge_type_value.upper(), edge_type_value.lower())

    def _describe_dependency(
        self, edge: GraphEdge, dep_node: GraphNode,
        target_node: GraphNode, operation: str
    ) -> str:
        verb = self._edge_verb(edge.edge_type.value)
        if operation == "DELETE":
            return (
                f"{dep_node.name} {verb} {target_node.name}. "
                f"Deleting {target_node.name} will break this dependency."
            )
        elif operation in ("MOVE", "RENAME"):
            return (
                f"{dep_node.name} {verb} {target_node.name} at its current path. "
                f"After {operation.lower()}, this reference may become invalid."
            )
        elif operation == "MODIFY":
            return (
                f"{dep_node.name} {verb} {target_node.name}. "
                f"Modifying {target_node.name} may affect {dep_node.name}."
            )
        return f"{dep_node.name} {verb} {target_node.name}."

    def _assess_edge_risk(self, edge: GraphEdge, operation: str) -> RiskLevel:
        high_risk_edges = {EdgeType.IMPORTS, EdgeType.LOADS, EdgeType.DEPENDS_ON, EdgeType.EXECUTES}
        medium_risk_edges = {EdgeType.READS, EdgeType.CONFIGURES, EdgeType.REFERENCES}

        if operation == "DELETE":
            if edge.edge_type in high_risk_edges:
                return RiskLevel.HIGH
            elif edge.edge_type == EdgeType.READS:
                return RiskLevel.HIGH  # Reading script will crash with FileNotFoundError
            elif edge.edge_type in medium_risk_edges:
                return RiskLevel.MEDIUM
        elif operation in ("MOVE", "RENAME"):
            if edge.edge_type in high_risk_edges:
                return RiskLevel.HIGH
            elif edge.edge_type in medium_risk_edges:
                return RiskLevel.HIGH  # Path references break on rename/move
        elif operation == "MODIFY":
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def _compute_overall_risk_with_env(
        self,
        operation: str,
        target_node: GraphNode,
        affected: List[ImpactedFile],
        environment: List[ImpactedFile],
        downstream: List[ImpactedFile],
        uncertain: List[ImpactedFile],
        is_folder: bool,
        folder_descendants: List[GraphNode],
        is_asset_or_doc: bool,
        has_critical_files: bool,
    ) -> RiskLevel:
        import os
        try:
            target_norm = os.path.normcase(os.path.abspath(target_node.path))
        except Exception:
            target_norm = os.path.normcase(target_node.path)

        # 1. Critical system dependency -> CRITICAL
        is_critical_system = (
            any(k in target_norm for k in ("system32", "syswow64", "\\windows\\", "system volume information", "$recycle.bin"))
            or (len(Path(target_norm).parts) <= 1)
            or any(f.risk_level == RiskLevel.CRITICAL for f in environment)
        )
        if is_critical_system:
            return RiskLevel.CRITICAL

        # 2. Active project/tool dependency -> HIGH
        confirmed_affected = [f for f in affected if f.confidence in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.LIKELY)]
        has_high_project_dep = any(f.risk_level in (RiskLevel.HIGH, RiskLevel.BLOCKED) for f in confirmed_affected)

        has_active_env_dep = any(
            f.risk_level == RiskLevel.HIGH or f.relationship == "ACTIVE_DEPENDENCY"
            for f in environment
        )

        if has_high_project_dep or has_active_env_dep:
            return RiskLevel.HIGH

        if is_folder and folder_descendants and operation in ("DELETE", "MOVE", "RENAME") and not is_asset_or_doc and has_critical_files:
            return RiskLevel.HIGH if affected else RiskLevel.MEDIUM

        # 3. Environment dependency -> MEDIUM
        if environment:
            return RiskLevel.MEDIUM

        if confirmed_affected:
            return RiskLevel.MEDIUM

        if downstream:
            return RiskLevel.MEDIUM

        # 4. Cache / config only -> LOW
        target_name_lower = target_node.name.lower()
        is_cache_or_config = (
            target_name_lower.startswith(".")
            or target_name_lower.endswith(("_cache", ".cache"))
            or target_name_lower in ("cache", ".cache", "tmp", "temp", ".temp", ".tmp", ".gradle", ".android", ".anaconda", ".aws", ".azure", ".ssh", ".kube", "logs", ".logs")
        )
        if is_cache_or_config:
            return RiskLevel.LOW

        if is_asset_or_doc or not folder_descendants:
            return RiskLevel.SAFE

        return RiskLevel.SAFE

    def _compute_overall_risk(
        self,
        operation: str,
        affected: List[ImpactedFile],
        downstream: List[ImpactedFile],
        uncertain: List[ImpactedFile],
    ) -> RiskLevel:
        all_items = affected + downstream + uncertain
        if not all_items:
            return RiskLevel.NO_CONFIRMED_IMPACT

        confirmed = [f for f in all_items if f.confidence in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.LIKELY)]
        if not confirmed:
            return RiskLevel.LOW

        risk_priority = {
            RiskLevel.CRITICAL: 6,
            RiskLevel.BLOCKED: 5,
            RiskLevel.HIGH: 4,
            RiskLevel.MEDIUM: 3,
            RiskLevel.LOW: 2,
            RiskLevel.SAFE: 1,
            RiskLevel.NO_CONFIRMED_IMPACT: 0,
            RiskLevel.UNKNOWN: 0,
            RiskLevel.ANALYSIS_INCOMPLETE: 0,
        }
        max_item = max(confirmed, key=lambda f: risk_priority.get(f.risk_level, 0))
        return max_item.risk_level

    def _build_summary(
        self,
        target_node: GraphNode,
        operation: str,
        affected: List[ImpactedFile],
        downstream: List[ImpactedFile],
        uncertain: List[ImpactedFile],
        environment: Optional[List[ImpactedFile]] = None,
    ) -> str:
        confirmed = [f for f in affected if f.confidence in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.LIKELY)]
        n_confirmed = len(confirmed)
        n_downstream = len(downstream)
        env_items = environment or []

        parts = []
        if env_items:
            env_vars = list({f.name.split()[0] for f in env_items})
            vars_str = ", ".join(env_vars[:3])
            parts.append(f"Environment dependency detected: {vars_str} references '{target_node.name}'.")

        if n_confirmed:
            parts.append(f"{n_confirmed} confirmed dependent file{'s' if n_confirmed != 1 else ''} detected.")

        if n_downstream:
            parts.append(f"{n_downstream} downstream file{'s' if n_downstream != 1 else ''} may also be affected.")

        if not parts:
            target_name_lower = target_node.name.lower()
            if target_name_lower.startswith(".") or "cache" in target_name_lower:
                return (
                    f"'{target_node.name}' is a configuration/cache folder with no detected "
                    f"code or environment dependencies. Safe to remove or reset."
                )
            return (
                f"No confirmed dependent files or environment references found for {target_node.name}. "
                f"This {operation.lower()} appears safe based on static analysis."
            )

        parts.append(f"Operation: {operation} on {target_node.name}.")
        return " ".join(parts)

    # ── Legacy helper ──────────────────────────────────────────────────────────

    def _impact_to_consequence(self, impacted: ImpactedFile) -> ConsequenceItem:
        return ConsequenceItem(
            affected_node_id=impacted.path,
            affected_node_name=impacted.name,
            impact_type=impacted.impact_type.lower(),
            description=impacted.description,
            evidence_chain=impacted.evidence_chain,
            risk_level=impacted.risk_level,
            confidence=impacted.confidence,
        )
