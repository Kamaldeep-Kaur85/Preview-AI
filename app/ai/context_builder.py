"""
app/ai/context_builder.py

Builds structured, rich project context for on-device AI inference.
Translates project AST relationships, symbol references, and graph topology
into model-ready feature tensors without blindly scanning the entire filesystem.
"""
from __future__ import annotations
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

from app.graph.models import EdgeType, GraphEdge, GraphNode, NodeType
from app.graph.builder import StateGraph


class ProjectContextBuilder:
    """
    Constructs candidate evaluation vectors from StateGraph and AST analysis.
    For a given changed/selected file, extracts:
    - Direct and transitive dependency relationships
    - Symbol references and call chains
    - Relative directory locality and naming patterns
    - Graph centrality metrics
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root

    def build_candidate_features(
        self,
        target_path_or_name: str,
        operation: str,
        graph: StateGraph,
        max_candidates: int = 64,
    ) -> Tuple[List[GraphNode], np.ndarray, Dict[str, Any]]:
        """
        Builds feature matrix [N, 16] for candidate affected files.
        Returns:
            candidates: List of GraphNode objects evaluated
            features: np.ndarray of shape [len(candidates), 16], float32
            context_summary: Metadata dict about extracted context
        """
        target_node = graph.get_node(target_path_or_name)
        if not target_node:
            target_node = graph.find_node_by_name(Path(target_path_or_name).name)

        if not target_node:
            # Create a virtual node if not found
            t_path = Path(target_path_or_name)
            target_node = GraphNode(
                node_id=str(t_path),
                name=t_path.name,
                path=str(t_path),
                node_type=NodeType.SCRIPT if t_path.suffix == ".py" else NodeType.FILE,
            )

        is_target_folder = target_node.node_type == NodeType.FOLDER or Path(target_node.path).is_dir()
        folder_descendants: List[GraphNode] = []
        if is_target_folder:
            import os
            try:
                folder_norm = os.path.normcase(os.path.abspath(target_node.path))
                for nid, n in graph.nodes.items():
                    if nid != target_node.node_id:
                        n_norm = os.path.normcase(os.path.abspath(n.path))
                        if n_norm.startswith(folder_norm + os.sep) or n_norm.startswith(folder_norm + "/"):
                            folder_descendants.append(n)
            except Exception:
                pass

        nodes_to_check = [target_node] + folder_descendants

        # 1. Identify direct dependents and reachable graph nodes
        dependents: List[Tuple[GraphEdge, GraphNode]] = []
        direct_dep_ids: Dict[str, GraphEdge] = {}
        for item in nodes_to_check:
            for edge, dep_node in graph.get_dependents(item.node_id):
                if edge.edge_type == EdgeType.CONTAINS:
                    continue
                if dep_node.node_id == target_node.node_id:
                    continue
                if is_target_folder and dep_node in folder_descendants:
                    continue
                dependents.append((edge, dep_node))
                if dep_node.node_id not in direct_dep_ids:
                    direct_dep_ids[dep_node.node_id] = edge

        # Transitive BFS
        all_affected: List[Tuple[GraphEdge, GraphNode, int]] = []
        transitive_depths: Dict[str, int] = {}
        for item in nodes_to_check:
            for edge, dep_node, depth in graph.get_all_affected(item.node_id):
                if edge.edge_type == EdgeType.CONTAINS:
                    continue
                if dep_node.node_id == target_node.node_id:
                    continue
                if is_target_folder and dep_node in folder_descendants:
                    continue
                all_affected.append((edge, dep_node, depth))
                if dep_node.node_id not in transitive_depths or depth < transitive_depths[dep_node.node_id]:
                    transitive_depths[dep_node.node_id] = depth

        # 2. Select candidates (only nodes with confirmed or plausible connection/reference)
        candidate_map: Dict[str, GraphNode] = {}
        for edge, dep_node in dependents:
            if dep_node.node_id == target_node.node_id:
                continue
            if not is_target_folder and dep_node.node_type == NodeType.FOLDER:
                continue
            candidate_map[dep_node.node_id] = dep_node

        for edge, dep_node, _ in all_affected:
            if dep_node.node_id == target_node.node_id:
                continue
            if not is_target_folder and dep_node.node_type == NodeType.FOLDER:
                continue
            candidate_map[dep_node.node_id] = dep_node

        target_stem = Path(target_node.name).stem.lower()

        # Add files that might reference target by name or stem (e.g. test_auth.py for auth.py)
        # Avoid generic/common asset stems like screenshots, images, docs from matching unrelated files
        generic_stems = {"screenshot", "screenshots", "image", "images", "img", "doc", "docs", "file", "folder", "test", "tests", "data", "temp", "tmp"}
        if len(target_stem) >= 3 and target_stem not in generic_stems:
            for nid, node in graph.nodes.items():
                if node.node_id == target_node.node_id or node.node_type == NodeType.FOLDER:
                    continue
                if is_target_folder and node in folder_descendants:
                    continue
                n_stem = Path(node.name).stem.lower()
                if (target_stem in n_stem or n_stem in target_stem) and n_stem not in generic_stems:
                    candidate_map[nid] = node
                if len(candidate_map) >= max_candidates:
                    break

        # Check for textual references to the target name in existing graph edges/evidence
        target_token = target_node.name.lower()
        if len(target_token) >= 4 and len(candidate_map) < max_candidates:
            for edge in graph.edges:
                if edge.evidence:
                    for ev in edge.evidence:
                        if target_token in ev.raw_text.lower() or target_token in ev.target_path.lower():
                            src_node = graph.get_node(edge.source_id)
                            if src_node and src_node.node_id != target_node.node_id and (not is_target_folder or src_node not in folder_descendants):
                                candidate_map[src_node.node_id] = src_node
                                break

        candidate_list = list(candidate_map.values())
        if not candidate_list:
            # Fallback: empty candidates - no component in the project has any connection to target
            return [], np.zeros((0, 16), dtype=np.float32), {"target": target_node.name}

        # 3. Vectorize features for each candidate
        # Operation one-hot
        op_upper = operation.upper()
        op_delete = 1.0 if "DELETE" in op_upper or "REMOVE" in op_upper else 0.0
        op_modify = 1.0 if "MODIFY" in op_upper or "CHANGE" in op_upper or "EDIT" in op_upper else 0.0
        op_rename_move = 1.0 if "RENAME" in op_upper or "MOVE" in op_upper else 0.0

        # Target in-degree
        target_in_degree = min(1.0, len(dependents) / 10.0)

        t_parts = Path(target_node.path).parts

        features = np.zeros((len(candidate_list), 16), dtype=np.float32)

        for i, cand in enumerate(candidate_list):
            is_direct = 1.0 if cand.node_id in direct_dep_ids else 0.0
            depth = transitive_depths.get(cand.node_id, 1 if is_direct else 999)
            path_distance_score = 1.0 / (depth + 1.0) if depth < 100 else 0.0

            # Symbol reference / edge count
            edge = direct_dep_ids.get(cand.node_id)
            ev_count = len(edge.evidence) if edge else 0
            symbol_ref_score = min(1.0, math.log1p(ev_count) / 3.0)

            # Test file flag
            c_name_lower = cand.name.lower()
            is_test = 1.0 if ("test" in c_name_lower or "tests" in Path(cand.path).parts) else 0.0

            # Edge type flags
            edge_type_val = edge.edge_type.value if edge else ""
            is_import = 1.0 if edge_type_val == EdgeType.IMPORTS.value else 0.0
            is_load = 1.0 if edge_type_val == EdgeType.LOADS.value else 0.0
            is_read = 1.0 if edge_type_val == EdgeType.READS.value else 0.0
            is_ref = 1.0 if edge_type_val == EdgeType.REFERENCES.value else 0.0
            is_cfg = 1.0 if edge_type_val in (EdgeType.CONFIGURES.value, EdgeType.DECLARES.value) else 0.0

            # Shared directory depth
            c_parts = Path(cand.path).parts
            shared_depth = 0
            for p1, p2 in zip(t_parts[:-1], c_parts[:-1]):
                if p1 == p2:
                    shared_depth += 1
                else:
                    break
            shared_dir_score = min(1.0, shared_depth / 5.0)

            # Candidate out-degree
            cand_deps = len(graph.get_dependencies(cand.node_id))
            cand_out_degree = min(1.0, cand_deps / 10.0)

            # Stem name overlap
            c_stem = Path(cand.name).stem.lower()
            stem_overlap = 1.0 if (target_stem in c_stem or c_stem in target_stem) else 0.0

            features[i] = [
                is_direct,               # 0
                path_distance_score,     # 1
                symbol_ref_score,        # 2
                is_test,                 # 3
                is_import,               # 4
                is_load,                 # 5
                is_read,                 # 6
                is_ref,                  # 7
                is_cfg,                  # 8
                op_delete,               # 9
                op_modify,               # 10
                op_rename_move,          # 11
                shared_dir_score,        # 12
                target_in_degree,        # 13
                cand_out_degree,         # 14
                stem_overlap,            # 15
            ]

        context_summary = {
            "target_node": target_node.name,
            "target_path": target_node.path,
            "operation": operation,
            "candidate_count": len(candidate_list),
            "direct_dependents": len(dependents),
            "transitive_dependents": len(all_affected),
        }

        return candidate_list, features, context_summary
