"""
app/simulation/virtual_state.py

Virtual state representation for simulation.
Never modifies the real filesystem — works on a copy-on-write model.
"""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.graph.models import GraphNode, NodeType


class VirtualState:
    """
    A copy-on-write representation of the project state.
    Operations are applied virtually without touching the real filesystem.
    """

    def __init__(self, nodes: Dict[str, GraphNode]):
        # Deep copy so we never mutate the original graph's nodes
        self.nodes: Dict[str, GraphNode] = {
            k: copy.deepcopy(v) for k, v in nodes.items()
        }
        self.changes: List[dict] = []  # Log of changes applied

    def delete(self, node_id: str) -> bool:
        """Virtually delete a node (cascades to descendants if folder)."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.exists = False
            self.changes.append({
                "type": "DELETE",
                "target": node_id,
                "name": node.name,
            })
            # If this is a folder, also virtually delete all descendant files and subfolders
            if node.node_type == NodeType.FOLDER or Path(node.path).is_dir():
                import os
                folder_norm = os.path.normcase(os.path.abspath(node.path))
                for child_id, child_node in self.nodes.items():
                    if child_node.exists and child_id != node_id:
                        child_norm = os.path.normcase(os.path.abspath(child_node.path))
                        if child_norm.startswith(folder_norm + os.sep) or child_norm.startswith(folder_norm + "/"):
                            child_node.exists = False
                            self.changes.append({
                                "type": "DELETE",
                                "target": child_id,
                                "name": child_node.name,
                            })
            return True
        return False

    def move(self, node_id: str, new_path: str) -> bool:
        """Virtually move a node to a new path."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            old_path = node.path
            if "/" in old_path and "\\" not in old_path:
                new_path = new_path.replace("\\", "/")
            new_p = Path(new_path)
            # Update node
            new_node = copy.deepcopy(node)
            new_node.node_id = new_path
            new_node.path = new_path
            new_node.name = new_p.name
            # Mark old as deleted
            node.exists = False
            # Add new node
            self.nodes[new_path] = new_node
            self.changes.append({
                "type": "MOVE",
                "target": node_id,
                "old_path": old_path,
                "new_path": new_path,
            })
            # If this is a folder, also update descendant paths
            if node.node_type == NodeType.FOLDER or Path(node.path).is_dir():
                import os
                folder_norm = os.path.normcase(os.path.abspath(node.path))
                for child_id, child_node in list(self.nodes.items()):
                    if child_node.exists and child_id != node_id:
                        child_norm = os.path.normcase(os.path.abspath(child_node.path))
                        if child_norm.startswith(folder_norm + os.sep) or child_norm.startswith(folder_norm + "/"):
                            rel = child_node.path[len(old_path):].lstrip("/\\")
                            child_new_path = str(Path(new_path) / rel)
                            if "/" in child_node.path and "\\" not in child_node.path:
                                child_new_path = child_new_path.replace("\\", "/")
                            child_new = copy.deepcopy(child_node)
                            child_new.node_id = child_new_path
                            child_new.path = child_new_path
                            child_node.exists = False
                            self.nodes[child_new_path] = child_new
                            self.changes.append({
                                "type": "MOVE",
                                "target": child_id,
                                "old_path": child_node.path,
                                "new_path": child_new_path,
                            })
            return True
        return False

    def rename(self, node_id: str, new_name: str) -> bool:
        """Virtually rename a node."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            old_path = node.path
            parent = str(Path(old_path).parent)
            new_path = str(Path(parent) / new_name)
            if "/" in old_path and "\\" not in old_path:
                new_path = new_path.replace("\\", "/")
            return self.move(node_id, new_path)
        return False

    def modify(self, node_id: str, description: str = "") -> bool:
        """Virtually mark a node as modified."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.metadata["modified_in_simulation"] = True
            self.changes.append({
                "type": "MODIFY",
                "target": node_id,
                "name": node.name,
                "description": description,
            })
            return True
        return False

    def create(self, path_or_name: str) -> bool:
        """Virtually create a node."""
        node_id = str(Path(path_or_name).resolve()) if Path(path_or_name).is_absolute() else path_or_name
        p = Path(path_or_name)
        node_type = NodeType.FOLDER if (path_or_name.endswith(("/", "\\")) or not p.suffix) else NodeType.FILE
        new_node = GraphNode(
            node_id=node_id,
            name=p.name or path_or_name,
            path=node_id,
            node_type=node_type,
            size_bytes=0,
            modified_time=0.0,
            extension=p.suffix.lower(),
            exists=True,
            metadata={"created_in_simulation": True},
        )
        self.nodes[node_id] = new_node
        self.changes.append({
            "type": "CREATE",
            "target": node_id,
            "name": new_node.name,
        })
        return True

    def get_existing_nodes(self) -> Dict[str, GraphNode]:
        """Return only nodes that still 'exist' in the virtual state."""
        return {k: v for k, v in self.nodes.items() if v.exists}

    def get_removed_nodes(self) -> Dict[str, GraphNode]:
        """Return nodes that were removed during simulation."""
        return {k: v for k, v in self.nodes.items() if not v.exists}

    def get_changes_summary(self) -> List[dict]:
        """Return list of all changes applied in this simulation."""
        return list(self.changes)
