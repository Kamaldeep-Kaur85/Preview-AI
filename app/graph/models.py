"""
app/graph/models.py

Node, Edge, and Evidence dataclasses for the PreView AI dependency graph.
These are deterministic data structures — no AI involved.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Any
import time


class NodeType(str, Enum):
    FILE = "FILE"
    FOLDER = "FOLDER"
    SCRIPT = "SCRIPT"
    PACKAGE = "PACKAGE"
    CONFIG = "CONFIG"
    APPLICATION = "APPLICATION"
    UNKNOWN = "UNKNOWN"


class EdgeType(str, Enum):
    IMPORTS = "IMPORTS"
    LOADS = "LOADS"
    READS = "READS"
    REFERENCES = "REFERENCES"
    DEPENDS_ON = "DEPENDS_ON"
    CONFIGURES = "CONFIGURES"
    EXECUTES = "EXECUTES"
    LOCATED_IN = "LOCATED_IN"
    DECLARES = "DECLARES"
    CONTAINS = "CONTAINS"


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    BLOCKED = "BLOCKED"
    NO_CONFIRMED_IMPACT = "NO CONFIRMED IMPACT"
    ANALYSIS_INCOMPLETE = "ANALYSIS INCOMPLETE"
    # Legacy alias kept for backward compat — do not display to user
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    CONFIRMED = "CONFIRMED"       # Verified by static analysis
    LIKELY = "LIKELY"             # Strong heuristic evidence
    POSSIBLE = "POSSIBLE"         # Weak/indirect evidence
    UNCERTAIN = "UNCERTAIN"       # Cannot be determined


class ChangeEventType(str, Enum):
    CREATE = "CREATE"
    DELETE = "DELETE"
    MODIFY = "MODIFY"
    MOVE = "MOVE"
    RENAME = "RENAME"


@dataclass
class ChangeEvent:
    """A detected filesystem change event."""
    event_type: ChangeEventType
    path: str                         # Affected path (after change)
    old_path: Optional[str] = None    # For RENAME/MOVE — original path
    timestamp: float = field(default_factory=time.time)
    source: str = "USER_MADE"         # "USER_MADE" or "AI_PROPOSED"

    @property
    def display_name(self) -> str:
        return Path(self.path).name

    @property
    def old_display_name(self) -> Optional[str]:
        return Path(self.old_path).name if self.old_path else None

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "path": self.path,
            "old_path": self.old_path,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class EvidenceItem:
    """A single piece of evidence supporting a relationship."""
    source_path: str
    target_path: str
    relation: EdgeType
    method: str                   # e.g., "ast_import", "string_reference", "config_key"
    line_number: Optional[int] = None
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    raw_text: Optional[str] = None   # The actual line of code / config entry

    def to_dict(self) -> dict:
        return {
            "source": self.source_path,
            "target": self.target_path,
            "relation": self.relation.value,
            "method": self.method,
            "line_number": self.line_number,
            "confidence": self.confidence.value,
            "raw_text": self.raw_text,
        }

    def __str__(self) -> str:
        loc = f":{self.line_number}" if self.line_number else ""
        src_name = Path(self.source_path).name if not self.source_path.startswith("package:") else self.source_path
        tgt_name = Path(self.target_path).name if not self.target_path.startswith("package:") else self.target_path
        return (
            f"{src_name}{loc} "
            f"\u2192 {self.relation.value} \u2192 "
            f"{tgt_name} "
            f"[{self.confidence.value}]"
        )


@dataclass
class GraphNode:
    """Represents a file, folder, package, or other project object."""
    node_id: str                  # Unique stable ID (usually absolute path)
    name: str                     # Display name
    path: str                     # Absolute path
    node_type: NodeType
    size_bytes: int = 0
    modified_time: float = 0.0
    extension: str = ""
    exists: bool = True
    metadata: dict = field(default_factory=dict)
    # UI state — set by impact analysis, not persisted
    impact_state: str = "normal"  # "normal" | "changed" | "affected" | "uncertain"

    @classmethod
    def from_path(cls, path: Path, node_type: Optional[NodeType] = None) -> "GraphNode":
        """Create a GraphNode from a filesystem Path."""
        if node_type is None:
            node_type = cls._infer_type(path)
        stat = path.stat() if path.exists() else None
        return cls(
            node_id=str(path),
            name=path.name,
            path=str(path),
            node_type=node_type,
            size_bytes=stat.st_size if stat else 0,
            modified_time=stat.st_mtime if stat else 0.0,
            extension=path.suffix.lower(),
            exists=path.exists(),
        )

    @staticmethod
    def _infer_type(path: Path) -> NodeType:
        if path.is_dir():
            return NodeType.FOLDER
        suffix = path.suffix.lower()
        if suffix == ".py":
            return NodeType.SCRIPT
        if suffix in (".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env"):
            return NodeType.CONFIG
        if suffix in (".txt",) and "requirements" in path.name.lower():
            return NodeType.CONFIG
        return NodeType.FILE

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "path": self.path,
            "node_type": self.node_type.value,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "extension": self.extension,
            "exists": self.exists,
            "impact_state": self.impact_state,
        }


@dataclass
class GraphEdge:
    """A directed relationship between two graph nodes."""
    source_id: str                # Source node_id
    target_id: str                # Target node_id
    edge_type: EdgeType
    evidence: List[EvidenceItem] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED

    @property
    def key(self) -> tuple:
        return (self.source_id, self.target_id, self.edge_type.value)

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "edge_type": self.edge_type.value,
            "confidence": self.confidence.value,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class ImpactedFile:
    """
    A single file confirmed or predicted to be impacted by a change.
    This is the core UI data object — drives the affected-files table.
    Answers: WHAT IS AFFECTED? HOW? WHY?
    """
    path: str                              # Absolute path
    name: str                              # Display name
    impact_type: str                       # "DIRECT" | "DEPENDENCY" | "DOWNSTREAM" | "UNCERTAIN"
    relationship: str                      # e.g. "READS", "IMPORTS", "LOADS"
    confidence: ConfidenceLevel
    risk_level: RiskLevel
    description: str                       # Human-readable impact description
    evidence_summary: str                  # One-line evidence text
    evidence_chain: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "impact_type": self.impact_type,
            "relationship": self.relationship,
            "confidence": self.confidence.value,
            "risk_level": self.risk_level.value,
            "description": self.description,
            "evidence_summary": self.evidence_summary,
            "evidence": [e.to_dict() for e in self.evidence_chain],
        }


@dataclass
class ImpactResult:
    """
    The complete, structured impact analysis result.
    Authoritative output of the consequence engine.
    Answers: WHAT CHANGED? WHAT IS AFFECTED? HOW? WHY?
    """
    # What changed
    changed_object: str           # Name of changed file/folder
    changed_path: str             # Absolute path
    operation: str                # DELETE / MOVE / RENAME / MODIFY / CREATE
    source: str = "AI_PROPOSED"   # "AI_PROPOSED" | "USER_MADE"

    # What is affected
    direct_impacts: List[ImpactedFile] = field(default_factory=list)
    affected_files: List[ImpactedFile] = field(default_factory=list)   # first-order
    environment_dependencies: List[ImpactedFile] = field(default_factory=list) # separate environment dependencies
    downstream_files: List[ImpactedFile] = field(default_factory=list) # second+ order
    uncertain_files: List[ImpactedFile] = field(default_factory=list)

    # Overall assessment
    risk: RiskLevel = RiskLevel.SAFE
    analysis_complete: bool = True
    analysis_time_ms: float = 0.0
    summary: str = ""

    # Snapdragon On-Device AI Metadata
    backend_used: str = "ONNX Runtime"
    accelerator_used: str = "CPU"
    inference_time_ms: float = 0.0

    # For MOVE/RENAME
    destination: Optional[str] = None

    @property
    def all_impacted(self) -> List[ImpactedFile]:
        return (
            self.direct_impacts
            + self.affected_files
            + self.environment_dependencies
            + self.downstream_files
            + self.uncertain_files
        )

    @property
    def confirmed_count(self) -> int:
        return sum(
            1 for f in self.all_impacted
            if f.confidence in (ConfidenceLevel.CONFIRMED, ConfidenceLevel.LIKELY)
        )

    @property
    def total_affected(self) -> int:
        return len(self.all_impacted)

    def to_dict(self) -> dict:
        return {
            "changed_object": self.changed_object,
            "changed_path": self.changed_path,
            "operation": self.operation,
            "source": self.source,
            "direct_impacts": [f.to_dict() for f in self.direct_impacts],
            "affected_files": [f.to_dict() for f in self.affected_files],
            "environment_dependencies": [f.to_dict() for f in self.environment_dependencies],
            "downstream_files": [f.to_dict() for f in self.downstream_files],
            "uncertain_files": [f.to_dict() for f in self.uncertain_files],
            "risk": self.risk.value,
            "analysis_complete": self.analysis_complete,
            "analysis_time_ms": self.analysis_time_ms,
            "confirmed_count": self.confirmed_count,
            "total_affected": self.total_affected,
            "summary": self.summary,
        }


@dataclass
class ConsequenceItem:
    """A single predicted consequence of an action. Legacy — use ImpactedFile for new code."""
    affected_node_id: str
    affected_node_name: str
    impact_type: str              # "direct", "dependency", "secondary", "uncertain"
    description: str
    evidence_chain: List[EvidenceItem] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED

    def to_dict(self) -> dict:
        return {
            "affected_node": self.affected_node_name,
            "impact_type": self.impact_type,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence.value,
            "evidence": [e.to_dict() for e in self.evidence_chain],
        }


@dataclass
class StructuredAction:
    """A validated, structured action parsed from user intent."""
    operation: str                # "DELETE", "MOVE", "RENAME", "MODIFY", "CREATE", "COPY"
    target: str                   # Primary target path
    destination: Optional[str] = None   # For MOVE/RENAME/COPY
    scope: str = "single_file"
    requires_analysis: bool = True
    raw_intent: str = ""          # Original user text
    content: Optional[str] = None
    new_content: Optional[str] = None
    diff: Optional[str] = None
    target_value: Optional[str] = None
    new_value: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    risk: str = "LOW"
    reversible: bool = True
    affected_files: List[str] = field(default_factory=list)

    VALID_OPERATIONS = {"DELETE", "MOVE", "RENAME", "MODIFY", "CREATE", "COPY", "CREATE_FOLDER", "SEARCH", "ANALYZE"}

    @property
    def source(self) -> str:
        return self.target

    def is_valid(self) -> bool:
        return (
            self.operation in self.VALID_OPERATIONS
            and bool(self.target)
        )

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "target": self.target,
            "source": self.target,
            "destination": self.destination,
            "scope": self.scope,
            "requires_analysis": self.requires_analysis,
            "raw_intent": self.raw_intent,
            "diff": self.diff,
            "reasons": self.reasons,
            "risk": self.risk,
            "reversible": self.reversible,
            "affected_files": self.affected_files,
        }
