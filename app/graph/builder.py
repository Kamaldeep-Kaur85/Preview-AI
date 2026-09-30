"""
app/graph/builder.py

Builds the state/dependency graph from scanned filesystem nodes
and parsed relationships. Deterministic — no AI.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from app.graph.models import (
    GraphNode, GraphEdge, EdgeType, EvidenceItem,
    ConfidenceLevel, NodeType,
)
from app.parsing.python_parser import PythonParser
from app.parsing.config_parser import ConfigParser
from app.parsing.reference_detector import ReferenceDetector
from app.state.scanner import FileScanner


class StateGraph:
    """
    The central dependency graph for a project.
    Nodes = files/folders/packages.
    Edges = relationships (IMPORTS, LOADS, READS, REFERENCES, etc.)
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self._edge_index: Dict[tuple, GraphEdge] = {}  # (src, tgt, type) -> edge
        self.build_time_ms: float = 0.0
        self.project_root: Optional[Path] = project_root
        self.files_indexed: int = 0
        self.files_changed: int = 0
        self.relationships: int = 0

    @property
    def index_summary(self) -> str:
        return f"Index ready: Files indexed: {self.files_indexed}, Changed: {self.files_changed}, Relationships: {self.relationships}"

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def add_node(self, node: GraphNode):
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge):
        key = edge.key
        if key in self._edge_index:
            # Merge evidence into existing edge
            existing = self._edge_index[key]
            existing.evidence.extend(edge.evidence)
        else:
            self.edges.append(edge)
            self._edge_index[key] = edge

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        node = self.nodes.get(node_id)
        if node:
            return node
        import os
        try:
            norm_id = os.path.normcase(os.path.abspath(node_id))
            for nid, n in self.nodes.items():
                if os.path.normcase(os.path.abspath(nid)) == norm_id:
                    return n
        except Exception:
            pass
        return None

    def find_node_by_name(self, name: str) -> Optional[GraphNode]:
        """Find a node by its filename (case-insensitive)."""
        name_lower = name.lower()
        for node in self.nodes.values():
            if node.name.lower() == name_lower:
                return node
        return None

    def find_nodes_by_name(self, name: str) -> List[GraphNode]:
        """Find all nodes matching a filename."""
        name_lower = name.lower()
        return [n for n in self.nodes.values() if n.name.lower() == name_lower]

    def get_dependents(self, node_id: str) -> List[Tuple[GraphEdge, GraphNode]]:
        """Get all nodes that depend ON this node (incoming edges TO this node)."""
        results = []
        import os
        try:
            norm_target = os.path.normcase(os.path.abspath(node_id))
        except Exception:
            norm_target = node_id.lower()
        for edge in self.edges:
            matches = False
            if edge.target_id == node_id:
                matches = True
            else:
                try:
                    if os.path.normcase(os.path.abspath(edge.target_id)) == norm_target:
                        matches = True
                except Exception:
                    pass
            if matches:
                source_node = self.get_node(edge.source_id)
                if source_node:
                    results.append((edge, source_node))
        return results

    def get_dependencies(self, node_id: str) -> List[Tuple[GraphEdge, GraphNode]]:
        """Get all nodes this node depends on (outgoing edges FROM this node)."""
        results = []
        import os
        try:
            norm_src = os.path.normcase(os.path.abspath(node_id))
        except Exception:
            norm_src = node_id.lower()
        for edge in self.edges:
            matches = False
            if edge.source_id == node_id:
                matches = True
            else:
                try:
                    if os.path.normcase(os.path.abspath(edge.source_id)) == norm_src:
                        matches = True
                except Exception:
                    pass
            if matches:
                target_node = self.get_node(edge.target_id)
                if target_node:
                    results.append((edge, target_node))
        return results

    def get_all_affected(self, node_id: str, visited: Optional[Set[str]] = None) -> List[Tuple[GraphEdge, GraphNode, int]]:
        """
        BFS: Get all transitively affected nodes if this node is removed/changed.
        Returns list of (edge, node, depth).
        """
        if visited is None:
            visited = set()
        visited.add(node_id)
        results = []
        for edge, dep_node in self.get_dependents(node_id):
            if dep_node.node_id not in visited:
                results.append((edge, dep_node, 1))
                visited.add(dep_node.node_id)
                # Recurse for secondary impacts
                for sub_edge, sub_node, sub_depth in self.get_all_affected(dep_node.node_id, visited):
                    results.append((sub_edge, sub_node, sub_depth + 1))
        return results

    def to_dict(self) -> dict:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "build_time_ms": self.build_time_ms,
            "files_indexed": self.files_indexed,
            "files_changed": self.files_changed,
            "relationships": self.relationships,
            "index_summary": self.index_summary,
        }


class GraphBuilder:
    """
    Builds a StateGraph from a project directory.
    Phase 1: Scan filesystem
    Phase 2: Parse Python files (AST)
    Phase 3: Parse config files
    Phase 4: Detect cross-file references
    """

    def __init__(
        self,
        project_root: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
        cache: Optional[Any] = None,
    ):
        self.project_root = project_root.resolve()
        self.progress_callback = progress_callback
        self.cache = cache
        self.python_parser = PythonParser(project_root=self.project_root)
        self.config_parser = ConfigParser()

    def _log(self, msg: str):
        if self.progress_callback:
            self.progress_callback(msg)

    def build(self) -> StateGraph:
        """Build the complete state graph for the project with caching."""
        graph = StateGraph(project_root=self.project_root)
        start = time.monotonic()

        # Phase 1: Scan filesystem
        self._log("Scanning filesystem...")
        scanner = FileScanner(
            root=self.project_root,
            progress_callback=self.progress_callback,
        )
        nodes = scanner.scan()
        for node in nodes.values():
            graph.add_node(node)

        # Connect folder containment hierarchy
        for node in list(nodes.values()):
            if node.node_id != str(self.project_root):
                parent_dir = str(Path(node.path).parent)
                if parent_dir in graph.nodes and parent_dir != node.node_id:
                    graph.add_edge(GraphEdge(
                        source_id=parent_dir,
                        target_id=node.node_id,
                        edge_type=EdgeType.CONTAINS,
                        confidence=ConfidenceLevel.CONFIRMED,
                    ))

        all_filenames = scanner.get_all_filenames(nodes)

        # Phase 2: Parse Python files
        self._log("Analyzing Python files...")
        changed_count = 0
        python_files = scanner.get_python_files(nodes)
        for pyfile in python_files:
            if self._parse_python_file(pyfile, graph, all_filenames):
                changed_count += 1

        # Phase 3: Parse config files
        self._log("Analyzing config files...")
        config_files = scanner.get_config_files(nodes)
        for cfgfile in config_files:
            if self._parse_config_file(cfgfile, graph, all_filenames):
                changed_count += 1

        # Phase 4: Cross-file reference detection
        self._log("Detecting cross-file references...")
        ref_detector = ReferenceDetector(known_filenames=all_filenames)
        for node in list(graph.nodes.values()):
            if node.node_type == NodeType.FOLDER:
                continue
            # Only scan text-like files for references
            if node.extension in (".py", ".json", ".yaml", ".yml", ".toml",
                                  ".cfg", ".ini", ".env", ".txt", ".md",
                                  ".sh", ".bat", ".cmd", ".ps1"):
                self._detect_references(Path(node.path), ref_detector, graph)

        if self.cache:
            try:
                self.cache.commit()
            except Exception:
                pass

        elapsed = time.monotonic() - start
        graph.build_time_ms = elapsed * 1000
        graph.files_indexed = len([n for n in nodes.values() if n.node_type != NodeType.FOLDER])
        graph.files_changed = changed_count if self.cache else graph.files_indexed
        graph.relationships = graph.edge_count
        self._log(f"Index ready: Files indexed: {graph.files_indexed}, Changed: {graph.files_changed}, Relationships: {graph.relationships} in {graph.build_time_ms:.0f}ms")

        return graph

    def incremental_update_file(
        self,
        graph: StateGraph,
        filepath: Path,
        event_type: str = "MODIFY",
    ) -> Tuple[StateGraph, List[str]]:
        """
        High-speed incremental graph update for a single changed file.
        Only reparses the modified file and updates affected edges.
        """
        t0 = time.monotonic()
        path_str = str(filepath.resolve())
        affected_dependents: List[str] = []

        if path_str in graph.nodes:
            affected_dependents = [node.path for _, node in graph.get_dependents(path_str)]

        ev = str(event_type).upper()
        if ev in ("DELETE", "REMOVE", "DELETED"):
            graph.nodes.pop(path_str, None)
            graph.edges = [e for e in graph.edges if e.source_id != path_str and e.target_id != path_str]
            graph._edge_index = {k: v for k, v in graph._edge_index.items()
                                 if v.source_id != path_str and v.target_id != path_str}
            if self.cache:
                self.cache.delete_file(path_str)

        elif ev in ("MODIFY", "CREATE", "CHANGE", "MODIFIED", "CREATED"):
            if not filepath.exists():
                return graph, affected_dependents

            try:
                stat = filepath.stat()
            except OSError:
                return graph, affected_dependents

            if path_str not in graph.nodes:
                node = GraphNode.from_path(filepath)
                graph.add_node(node)
                parent_dir = str(filepath.parent)
                if parent_dir in graph.nodes and parent_dir != path_str:
                    graph.add_edge(GraphEdge(
                        source_id=parent_dir,
                        target_id=path_str,
                        edge_type=EdgeType.CONTAINS,
                        confidence=ConfidenceLevel.CONFIRMED,
                    ))
            else:
                graph.nodes[path_str].modified_time = stat.st_mtime
                graph.nodes[path_str].size_bytes = stat.st_size

            # Remove previous outgoing edges from this file
            graph.edges = [e for e in graph.edges if e.source_id != path_str]
            graph._edge_index = {k: v for k, v in graph._edge_index.items() if v.source_id != path_str}

            all_filenames = {n.name for n in graph.nodes.values()}

            # Reparse only this modified file
            ext = filepath.suffix.lower()
            if ext == ".py":
                if self.cache:
                    self.cache.delete_file(path_str)
                self._parse_python_file(filepath, graph, all_filenames)
            elif ext in (".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env", ".txt"):
                if self.cache:
                    self.cache.delete_file(path_str)
                self._parse_config_file(filepath, graph, all_filenames)

            # Update cache
            if self.cache:
                self.cache.upsert_file(
                    path=path_str,
                    name=filepath.name,
                    node_type=graph.nodes[path_str].node_type.value,
                    size_bytes=stat.st_size,
                    mtime=stat.st_mtime,
                    extension=ext,
                    analysis_done=True,
                )

            # Re-check dependents
            new_dependents = [node.path for _, node in graph.get_dependents(path_str)]
            affected_dependents = list(set(affected_dependents + new_dependents))

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        graph.build_time_ms = elapsed_ms
        graph.files_indexed = len([n for n in graph.nodes.values() if n.node_type != NodeType.FOLDER])
        graph.files_changed = getattr(graph, "files_changed", 0) + 1
        graph.relationships = graph.edge_count
        self._log(f"Incremental update: {filepath.name} — Index ready: Files indexed: {graph.files_indexed}, Changed: {graph.files_changed}, Relationships: {graph.relationships} in {elapsed_ms:.1f}ms")
        return graph, affected_dependents

    def _parse_python_file(self, filepath: Path, graph: StateGraph, all_filenames: Set[str]) -> bool:
        """Parse a Python file and add edges to the graph with AST caching. Returns True if parsed/changed, False if cached."""
        source_id = str(filepath.resolve())
        result = None
        was_changed = False

        if self.cache and filepath.exists():
            try:
                st = filepath.stat()
                result = self.cache.get_parsed_ast(source_id, st.st_mtime, st.st_size)
            except OSError:
                pass

        if result is None:
            was_changed = True
            result = self.python_parser.parse_file(filepath)
            if self.cache and filepath.exists():
                try:
                    st = filepath.stat()
                    self.cache.save_parsed_ast(source_id, st.st_mtime, st.st_size, result)
                    self.cache.upsert_file(
                        path=source_id,
                        name=filepath.name,
                        node_type=NodeType.SCRIPT.value,
                        size_bytes=st.st_size,
                        mtime=st.st_mtime,
                        extension=filepath.suffix.lower(),
                        analysis_done=True,
                    )
                except OSError:
                    pass
        source_id = str(filepath.resolve())

        # Process imports
        for imp in result.get("imports", []):
            module = imp["module"]
            # Try to resolve module to a local file
            candidates = self._resolve_import(module, filepath)
            for target_path in candidates:
                target_id = str(target_path)
                if target_id in graph.nodes:
                    evidence = EvidenceItem(
                        source_path=source_id,
                        target_path=target_id,
                        relation=EdgeType.IMPORTS,
                        method="ast_import",
                        line_number=imp.get("line"),
                        confidence=ConfidenceLevel.CONFIRMED,
                        raw_text=f"import {module}",
                    )
                    graph.add_edge(GraphEdge(
                        source_id=source_id,
                        target_id=target_id,
                        edge_type=EdgeType.IMPORTS,
                        evidence=[evidence],
                        confidence=ConfidenceLevel.CONFIRMED,
                    ))

        # Process file references (open, load, read_csv, etc.)
        for ref in result.get("file_references", []):
            resolved = self.python_parser.resolve_reference(
                ref["path"], filepath, self.project_root
            )
            if resolved:
                target_id = str(resolved)
                if target_id in graph.nodes:
                    # Determine edge type from function name
                    func = ref.get("function", "").lower()
                    target_ext = Path(target_id).suffix.lower()
                    if "load" in func or "pickle" in func or "torch" in func or "joblib" in func or target_ext in (".pkl", ".pickle", ".pt", ".pth", ".h5", ".hdf5", ".onnx", ".bin", ".weights"):
                        edge_type = EdgeType.LOADS
                    elif "read" in func:
                        edge_type = EdgeType.READS
                    elif "open" in func:
                        edge_type = EdgeType.READS
                    else:
                        edge_type = EdgeType.REFERENCES

                    evidence = EvidenceItem(
                        source_path=source_id,
                        target_path=target_id,
                        relation=edge_type,
                        method="ast_file_reference",
                        line_number=ref.get("line"),
                        confidence=ConfidenceLevel.CONFIRMED,
                        raw_text=ref.get("raw", ""),
                    )
                    graph.add_edge(GraphEdge(
                        source_id=source_id,
                        target_id=target_id,
                        edge_type=edge_type,
                        evidence=[evidence],
                        confidence=ConfidenceLevel.CONFIRMED,
                    ))
            else:
                # File not found but referenced — search by name
                ref_name = Path(ref["path"]).name
                target_node = graph.find_node_by_name(ref_name)
                if target_node:
                    func = ref.get("function", "").lower()
                    if "load" in func:
                        edge_type = EdgeType.LOADS
                    elif "read" in func:
                        edge_type = EdgeType.READS
                    else:
                        edge_type = EdgeType.REFERENCES

                    evidence = EvidenceItem(
                        source_path=source_id,
                        target_path=target_node.node_id,
                        relation=edge_type,
                        method="ast_file_reference_by_name",
                        line_number=ref.get("line"),
                        confidence=ConfidenceLevel.LIKELY,
                        raw_text=ref.get("raw", ""),
                    )
                    graph.add_edge(GraphEdge(
                        source_id=source_id,
                        target_id=target_node.node_id,
                        edge_type=edge_type,
                        evidence=[evidence],
                        confidence=ConfidenceLevel.LIKELY,
                    ))

        # Process string path references
        for sp in result.get("string_paths", []):
            raw_val = sp["value"]
            ref_name = Path(raw_val).name
            target_node = graph.find_node_by_name(ref_name)
            if target_node and target_node.node_id != source_id:
                evidence = EvidenceItem(
                    source_path=source_id,
                    target_path=target_node.node_id,
                    relation=EdgeType.REFERENCES,
                    method="string_path",
                    line_number=sp.get("line"),
                    confidence=ConfidenceLevel.POSSIBLE,
                    raw_text=raw_val,
                )
                graph.add_edge(GraphEdge(
                    source_id=source_id,
                    target_id=target_node.node_id,
                    edge_type=EdgeType.REFERENCES,
                    evidence=[evidence],
                    confidence=ConfidenceLevel.POSSIBLE,
                ))

            # Also check if path references a folder (e.g. "dataset/..." or "dataset")
            p_parts = Path(raw_val).parts
            if p_parts:
                first_part = p_parts[0].rstrip("/\\")
                folder_node = graph.find_node_by_name(first_part)
                if folder_node and folder_node.node_type == NodeType.FOLDER and folder_node.node_id != source_id:
                    ev_folder = EvidenceItem(
                        source_path=source_id,
                        target_path=folder_node.node_id,
                        relation=EdgeType.REFERENCES,
                        method="path_directory_reference",
                        line_number=sp.get("line"),
                        confidence=ConfidenceLevel.LIKELY,
                        raw_text=raw_val,
                    )
                    graph.add_edge(GraphEdge(
                        source_id=source_id,
                        target_id=folder_node.node_id,
                        edge_type=EdgeType.REFERENCES,
                        evidence=[ev_folder],
                        confidence=ConfidenceLevel.LIKELY,
                    ))

    def _parse_config_file(self, filepath: Path, graph: StateGraph, all_filenames: Set[str]) -> bool:
        """Parse a config file and add edges with AST/parse caching. Returns True if parsed/changed, False if cached."""
        source_id = str(filepath)
        result = None
        was_changed = False

        if self.cache and filepath.exists():
            try:
                st = filepath.stat()
                result = self.cache.get_parsed_ast(source_id, st.st_mtime, st.st_size)
            except OSError:
                pass

        if result is None:
            was_changed = True
            result = self.config_parser.parse_file(filepath)
            if self.cache and filepath.exists():
                try:
                    st = filepath.stat()
                    self.cache.save_parsed_ast(source_id, st.st_mtime, st.st_size, result)
                except OSError:
                    pass

        # Package dependencies from requirements.txt / pyproject.toml
        for pkg in result.get("packages", []):
            pkg_name = pkg["name"]
            # Create a virtual package node
            pkg_id = f"package:{pkg_name}"
            if pkg_id not in graph.nodes:
                graph.add_node(GraphNode(
                    node_id=pkg_id,
                    name=pkg_name,
                    path=pkg_id,
                    node_type=NodeType.PACKAGE,
                ))
            evidence = EvidenceItem(
                source_path=source_id,
                target_path=pkg_id,
                relation=EdgeType.DECLARES,
                method="config_dependency",
                confidence=ConfidenceLevel.CONFIRMED,
                raw_text=pkg.get("raw", pkg_name),
            )
            graph.add_edge(GraphEdge(
                source_id=source_id,
                target_id=pkg_id,
                edge_type=EdgeType.DECLARES,
                evidence=[evidence],
                confidence=ConfidenceLevel.CONFIRMED,
            ))

        # File references in config
        for ref in result.get("file_refs", []):
            ref_val = ref.get("value") or ref.get("path", "")
            if not ref_val:
                continue
            ref_name = Path(ref_val).name
            target_node = graph.find_node_by_name(ref_name)
            if target_node and target_node.node_id != source_id:
                evidence = EvidenceItem(
                    source_path=source_id,
                    target_path=target_node.node_id,
                    relation=EdgeType.CONFIGURES,
                    method="config_reference",
                    confidence=ConfidenceLevel.LIKELY,
                    raw_text=ref_val,
                )
                graph.add_edge(GraphEdge(
                    source_id=source_id,
                    target_id=target_node.node_id,
                    edge_type=EdgeType.CONFIGURES,
                    evidence=[evidence],
                    confidence=ConfidenceLevel.LIKELY,
                ))
        return was_changed

    def _detect_references(self, filepath: Path, detector: ReferenceDetector, graph: StateGraph):
        """Find cross-file references in any text file."""
        source_id = str(filepath)
        refs = detector.scan_file_for_known_names(filepath)
        for ref in refs:
            target_name = ref["target"]
            target_node = graph.find_node_by_name(target_name)
            if target_node and target_node.node_id != source_id:
                # Don't add duplicate edges that already exist with higher confidence
                existing_key = (source_id, target_node.node_id, EdgeType.REFERENCES.value)
                if existing_key not in graph._edge_index:
                    evidence = EvidenceItem(
                        source_path=source_id,
                        target_path=target_node.node_id,
                        relation=EdgeType.REFERENCES,
                        method="text_scan",
                        line_number=ref.get("line_number"),
                        confidence=ConfidenceLevel.POSSIBLE,
                        raw_text=ref.get("raw_text", ""),
                    )
                    graph.add_edge(GraphEdge(
                        source_id=source_id,
                        target_id=target_node.node_id,
                        edge_type=EdgeType.REFERENCES,
                        evidence=[evidence],
                        confidence=ConfidenceLevel.POSSIBLE,
                    ))

    def _resolve_import(self, module_name: str, from_file: Path) -> List[Path]:
        """Try to resolve a Python import to local file(s)."""
        parts = module_name.split(".")
        results = []

        # Try relative to project root
        for root in [self.project_root, from_file.parent]:
            # module.submodule -> module/submodule.py or module/submodule/__init__.py
            candidate = root / Path(*parts).with_suffix(".py")
            if candidate.exists():
                results.append(candidate.resolve())
            candidate_init = root / Path(*parts) / "__init__.py"
            if candidate_init.exists():
                results.append(candidate_init.resolve())

        return results

    def _get_all_filenames(self) -> Set[str]:
        """Return set of all filenames currently in the project root."""
        try:
            scanner = FileScanner(root=self.project_root)
            nodes = scanner.scan()
            return scanner.get_all_filenames(nodes)
        except Exception:
            return set()
