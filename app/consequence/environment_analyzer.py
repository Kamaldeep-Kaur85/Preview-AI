"""
app/consequence/environment_analyzer.py

Deterministic Environment Dependency Analyzer.
Inspects Windows environment variables (PATH, PYTHONPATH, JAVA_HOME,
ANDROID_HOME, ANDROID_SDK_ROOT, CONDA_* variables, and other runtime tools)
to detect whether a target file or folder is referenced by system or user
environment configurations.

Distinguishes:
  - ACTIVE_DEPENDENCY: Currently active runtime/interpreter or PATH-resolved binary.
  - CONFIGURATION_REFERENCE: Configured in system/user environment variables.
  - EXISTENCE_OF_SOFTWARE: Software exists on disk but is not referenced by environment.
  - INFERRED: Heuristic or indirect relationship.

Never invents dependencies. Evidence-backed deterministic analysis only.
"""
from __future__ import annotations

import os
import sys
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.graph.models import (
    ConfidenceLevel,
    EdgeType,
    EvidenceItem,
    ImpactedFile,
    RiskLevel,
)


@dataclass
class EnvironmentDependency:
    """A detected environment-level reference to a target path."""
    variable_name: str
    matched_path: str
    source: str                 # "User PATH", "System PATH", "User", "System", "Process"
    match_type: str             # "EXACT", "PARENT_DIRECTORY", "SUBDIRECTORY", "PATH_EXECUTABLE"
    category: str               # "ACTIVE_DEPENDENCY", "CONFIGURATION_REFERENCE", "EXISTENCE_OF_SOFTWARE", "INFERRED"
    risk_level: RiskLevel
    confidence: ConfidenceLevel
    description: str
    why_it_matters: str
    raw_value: str = ""

    def to_impacted_file(self) -> ImpactedFile:
        """Convert to canonical ImpactedFile model for consequence display."""
        ev = EvidenceItem(
            source_path=f"env:{self.variable_name}",
            target_path=self.matched_path,
            relation=EdgeType.REFERENCES,
            method="environment_variable_inspection",
            confidence=self.confidence,
            raw_text=f"{self.variable_name} ({self.source}) -> '{self.matched_path}' [{self.category}]",
        )
        return ImpactedFile(
            path=self.matched_path,
            name=f"{self.variable_name} [{self.source}]",
            impact_type="ENVIRONMENT_DEPENDENCY",
            relationship=self.category,
            confidence=self.confidence,
            risk_level=self.risk_level,
            description=self.description,
            evidence_summary=f"{self.variable_name} [{self.source}] references '{self.matched_path}' ({self.why_it_matters})",
            evidence_chain=[ev],
        )


class EnvironmentDependencyAnalyzer:
    """
    Analyzes environment variables (Process, User, and System) to detect
    external runtime and configuration dependencies on target paths.
    """

    KNOWN_TOOL_VARS = (
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "JAVA_HOME",
        "JDK_HOME",
        "ANDROID_HOME",
        "ANDROID_SDK_ROOT",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_EXE",
        "CONDA_PYTHON_EXE",
        "CONDA_ROOT",
        "CONDA_BAT",
        "VIRTUAL_ENV",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "GOROOT",
        "GOPATH",
        "NODE_PATH",
        "NVM_HOME",
        "NVM_SYMLINK",
        "DOTNET_ROOT",
        "GRADLE_HOME",
        "M2_HOME",
        "MAVEN_HOME",
        "FLUTTER_HOME",
        "CUDA_PATH",
        "CUDA_HOME",
    )

    def __init__(
        self,
        env: Optional[Dict[str, str]] = None,
        system_env: Optional[Dict[str, str]] = None,
        user_env: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize analyzer. If env, system_env, or user_env are provided,
        they override default discovery (useful for unit testing).
        """
        self._custom_mode = (env is not None or system_env is not None or user_env is not None)
        self.system_env: Dict[str, str] = system_env if system_env is not None else self._read_system_registry_env()
        self.user_env: Dict[str, str] = user_env if user_env is not None else self._read_user_registry_env()
        self.process_env: Dict[str, str] = env if env is not None else dict(os.environ)

    # ── Registry Discovery ───────────────────────────────────────────────────

    @staticmethod
    def _read_system_registry_env() -> Dict[str, str]:
        """Safely read Windows System environment variables from Registry."""
        if sys.platform != "win32":
            return {}
        try:
            import winreg
            result: Dict[str, str] = {}
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            ) as key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        if isinstance(val, str):
                            result[name] = os.path.expandvars(val)
                    except Exception:
                        continue
            return result
        except Exception:
            return {}

    @staticmethod
    def _read_user_registry_env() -> Dict[str, str]:
        """Safely read Windows User environment variables from Registry."""
        if sys.platform != "win32":
            return {}
        try:
            import winreg
            result: Dict[str, str] = {}
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment"
            ) as key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        if isinstance(val, str):
                            result[name] = os.path.expandvars(val)
                    except Exception:
                        continue
            return result
        except Exception:
            return {}

    # ── Primary Analysis ─────────────────────────────────────────────────────

    def analyze_target(self, target_path_or_name: str) -> List[EnvironmentDependency]:
        """
        Analyze whether target_path_or_name has environment-level dependencies.
        Returns a list of EnvironmentDependency objects with evidence.
        """
        if not target_path_or_name:
            return []

        # Normalize target path
        try:
            target_norm = os.path.normcase(os.path.abspath(target_path_or_name))
            target_obj = Path(target_norm)
        except Exception:
            target_norm = os.path.normcase(target_path_or_name)
            target_obj = Path(target_path_or_name)

        target_name = target_obj.name.lower()
        results: List[EnvironmentDependency] = []
        seen_keys: Set[Tuple[str, str, str]] = set()

        def _add_dep(dep: EnvironmentDependency):
            key = (dep.variable_name.upper(), dep.matched_path.lower(), dep.source)
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(dep)

        # 1. Analyze PATH entries (System PATH, User PATH, and Process PATH)
        self._analyze_path_entries(target_norm, target_name, target_obj, _add_dep)

        # 2. Analyze tool and runtime variables
        self._analyze_tool_variables(target_norm, target_name, target_obj, _add_dep)

        # 3. Analyze general environment variables matching target
        self._analyze_generic_env(target_norm, target_name, target_obj, _add_dep)

        # 4. Check if target is an executable or contains executables resolved via PATH
        self._analyze_resolved_executables(target_norm, target_name, target_obj, _add_dep)

        return results

    # ── PATH Analysis ────────────────────────────────────────────────────────

    def _analyze_path_entries(
        self,
        target_norm: str,
        target_name: str,
        target_obj: Path,
        add_dep,
    ):
        """Inspect System PATH, User PATH, and Process PATH entries."""
        path_sources = []

        # System PATH from registry
        sys_path = self._get_var_case_insensitive(self.system_env, "PATH")
        if sys_path:
            path_sources.append(("System PATH", "PATH", sys_path))

        # User PATH from registry
        usr_path = self._get_var_case_insensitive(self.user_env, "PATH")
        if usr_path:
            path_sources.append(("User PATH", "PATH", usr_path))

        # Process PATH (fallback or custom testing)
        proc_path = self._get_var_case_insensitive(self.process_env, "PATH")
        if proc_path and not path_sources:
            path_sources.append(("Process PATH", "PATH", proc_path))

        for source_name, var_name, path_str in path_sources:
            entries = [p.strip().strip('"') for p in path_str.split(os.pathsep) if p.strip()]
            for raw_entry in entries:
                try:
                    entry_norm = os.path.normcase(os.path.abspath(raw_entry))
                except Exception:
                    entry_norm = os.path.normcase(raw_entry)

                # A) Direct match: Target directory is an entry in PATH
                if target_norm == entry_norm:
                    is_active = self._is_active_runtime_path(target_norm)
                    category = "ACTIVE_DEPENDENCY" if is_active else "CONFIGURATION_REFERENCE"
                    risk = RiskLevel.HIGH if is_active else RiskLevel.MEDIUM
                    add_dep(EnvironmentDependency(
                        variable_name=var_name,
                        matched_path=raw_entry,
                        source=source_name,
                        match_type="EXACT",
                        category=category,
                        risk_level=risk,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"{var_name} ({source_name}) references this directory ('{raw_entry}').",
                        why_it_matters=f"Commands and binaries located in '{raw_entry}' will stop resolving in shell sessions if deleted.",
                        raw_value=path_str,
                    ))

                # B) Parent directory match: Target is parent of a PATH entry
                # e.g. Target is C:\Users\sai\anaconda3 and PATH has C:\Users\sai\anaconda3\Scripts
                elif entry_norm.startswith(target_norm + os.sep) or entry_norm.startswith(target_norm + "/"):
                    rel = entry_norm[len(target_norm):].lstrip("\\/")
                    is_active = self._is_active_runtime_path(target_norm)
                    category = "ACTIVE_DEPENDENCY" if is_active else "CONFIGURATION_REFERENCE"
                    risk = RiskLevel.HIGH if is_active else RiskLevel.MEDIUM
                    add_dep(EnvironmentDependency(
                        variable_name=var_name,
                        matched_path=raw_entry,
                        source=source_name,
                        match_type="PARENT_DIRECTORY",
                        category=category,
                        risk_level=risk,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"{var_name} ({source_name}) references subdirectory '{rel}' within this folder ('{raw_entry}').",
                        why_it_matters=f"Deleting this directory will delete configured PATH entry '{raw_entry}', breaking commands relying on it.",
                        raw_value=path_str,
                    ))

                # C) Subdirectory match: Target is inside a PATH directory
                elif target_norm.startswith(entry_norm + os.sep) or target_norm.startswith(entry_norm + "/"):
                    # Check if target is an executable or script
                    ext = target_obj.suffix.lower()
                    if ext in (".exe", ".bat", ".cmd", ".ps1", ".com", ".py"):
                        add_dep(EnvironmentDependency(
                            variable_name=var_name,
                            matched_path=raw_entry,
                            source=source_name,
                            match_type="PATH_EXECUTABLE",
                            category="ACTIVE_DEPENDENCY",
                            risk_level=RiskLevel.MEDIUM,
                            confidence=ConfidenceLevel.CONFIRMED,
                            description=f"Executable '{target_obj.name}' resides in {var_name} ({source_name}) entry '{raw_entry}'.",
                            why_it_matters=f"Executing '{target_obj.stem}' from terminal/tools will fail once deleted.",
                            raw_value=raw_entry,
                        ))

    # ── Tool & Runtime Variables ─────────────────────────────────────────────

    def _analyze_tool_variables(
        self,
        target_norm: str,
        target_name: str,
        target_obj: Path,
        add_dep,
    ):
        """Inspect JAVA_HOME, ANDROID_HOME, ANDROID_SDK_ROOT, CONDA_*, etc."""
        # Gather all sources
        all_vars: List[Tuple[str, str, str]] = []  # (source, var_name, var_value)

        # Registry user vars
        for k, v in self.user_env.items():
            if k.upper() != "PATH":
                all_vars.append(("User", k, v))

        # Registry system vars
        for k, v in self.system_env.items():
            if k.upper() != "PATH":
                all_vars.append(("System", k, v))

        # Process vars (include CONDA_*, VIRTUAL_ENV, etc.)
        for k, v in self.process_env.items():
            if k.upper() != "PATH":
                # Check if not already covered by User or System registry
                if k not in self.user_env and k not in self.system_env:
                    all_vars.append(("Process", k, v))

        # Filter to relevant variables
        for source, var_name, var_value in all_vars:
            v_upper = var_name.upper()
            is_candidate = (
                v_upper in self.KNOWN_TOOL_VARS
                or v_upper.startswith("CONDA_")
                or v_upper.endswith("_HOME")
                or v_upper.endswith("_ROOT")
                or v_upper.endswith("_PATH")
            )
            if not is_candidate:
                continue

            raw_val = var_value.strip().strip('"')
            if not raw_val:
                continue

            # Handle multi-path variables like PYTHONPATH
            if v_upper == "PYTHONPATH":
                val_entries = [p.strip().strip('"') for p in raw_val.split(os.pathsep) if p.strip()]
            else:
                val_entries = [raw_val]

            for entry in val_entries:
                try:
                    entry_norm = os.path.normcase(os.path.abspath(entry))
                except Exception:
                    entry_norm = os.path.normcase(entry)

                # Direct match
                if target_norm == entry_norm:
                    is_active = self._is_active_runtime_var(v_upper, target_norm)
                    category = "ACTIVE_DEPENDENCY" if is_active else "CONFIGURATION_REFERENCE"
                    risk = RiskLevel.HIGH if is_active else RiskLevel.MEDIUM
                    add_dep(EnvironmentDependency(
                        variable_name=var_name,
                        matched_path=entry,
                        source=source,
                        match_type="EXACT",
                        category=category,
                        risk_level=risk,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Environment variable {var_name} [{source}] is configured to this directory ('{entry}').",
                        why_it_matters=f"Applications or tools expecting {var_name} at this location will fail if deleted.",
                        raw_value=raw_val,
                    ))

                # Parent directory match (Target contains configured variable path)
                elif entry_norm.startswith(target_norm + os.sep) or entry_norm.startswith(target_norm + "/"):
                    rel = entry_norm[len(target_norm):].lstrip("\\/")
                    is_active = self._is_active_runtime_var(v_upper, target_norm)
                    category = "ACTIVE_DEPENDENCY" if is_active else "CONFIGURATION_REFERENCE"
                    risk = RiskLevel.HIGH if is_active else RiskLevel.MEDIUM
                    add_dep(EnvironmentDependency(
                        variable_name=var_name,
                        matched_path=entry,
                        source=source,
                        match_type="PARENT_DIRECTORY",
                        category=category,
                        risk_level=risk,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Environment variable {var_name} [{source}] points to '{rel}' inside this folder.",
                        why_it_matters=f"Deleting this folder removes the path '{entry}' configured by {var_name}.",
                        raw_value=raw_val,
                    ))

                # Subdirectory match (Target is inside configured tool root)
                elif target_norm.startswith(entry_norm + os.sep) or target_norm.startswith(entry_norm + "/"):
                    rel = target_norm[len(entry_norm):].lstrip("\\/")
                    add_dep(EnvironmentDependency(
                        variable_name=var_name,
                        matched_path=entry,
                        source=source,
                        match_type="SUBDIRECTORY",
                        category="CONFIGURATION_REFERENCE",
                        risk_level=RiskLevel.MEDIUM,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Target '{rel}' is located inside the {var_name} [{source}] root ('{entry}').",
                        why_it_matters=f"Modifying or deleting items inside {var_name} may break tool runtime stability.",
                        raw_value=raw_val,
                    ))

    # ── Generic Environment Variable Matching ────────────────────────────────

    def _analyze_generic_env(
        self,
        target_norm: str,
        target_name: str,
        target_obj: Path,
        add_dep,
    ):
        """Check other environment variables whose values point to target."""
        for env_dict, source in [
            (self.user_env, "User"),
            (self.system_env, "System"),
            (self.process_env, "Process"),
        ]:
            for k, v in env_dict.items():
                k_upper = k.upper()
                if (
                    k_upper == "PATH"
                    or k_upper in self.KNOWN_TOOL_VARS
                    or k_upper.startswith("CONDA_")
                ):
                    continue

                raw_val = v.strip().strip('"')
                if not raw_val or len(raw_val) < 3:
                    continue

                # Only evaluate values that look like filesystem paths
                if not (":" in raw_val or raw_val.startswith(("\\", "/"))):
                    continue

                try:
                    val_norm = os.path.normcase(os.path.abspath(raw_val))
                except Exception:
                    continue

                if target_norm == val_norm:
                    add_dep(EnvironmentDependency(
                        variable_name=k,
                        matched_path=raw_val,
                        source=source,
                        match_type="EXACT",
                        category="CONFIGURATION_REFERENCE",
                        risk_level=RiskLevel.MEDIUM,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Environment variable {k} [{source}] references this directory.",
                        why_it_matters=f"Services or scripts relying on {k} will fail to locate this path.",
                        raw_value=raw_val,
                    ))
                elif val_norm.startswith(target_norm + os.sep) or val_norm.startswith(target_norm + "/"):
                    add_dep(EnvironmentDependency(
                        variable_name=k,
                        matched_path=raw_val,
                        source=source,
                        match_type="PARENT_DIRECTORY",
                        category="CONFIGURATION_REFERENCE",
                        risk_level=RiskLevel.MEDIUM,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Environment variable {k} [{source}] points to '{raw_val}' inside this folder.",
                        why_it_matters=f"Deleting this directory removes the target of {k}.",
                        raw_value=raw_val,
                    ))

    # ── Resolved Executables via PATH ────────────────────────────────────────

    def _analyze_resolved_executables(
        self,
        target_norm: str,
        target_name: str,
        target_obj: Path,
        add_dep,
    ):
        """
        Check if target is an executable (or directly contains executables)
        that is currently resolved when looking up command names in PATH.
        """
        # If target is a file, check if it resolves via shutil.which
        if target_obj.suffix.lower() in (".exe", ".bat", ".cmd", ".ps1"):
            cmd_name = target_obj.stem
            resolved = shutil.which(cmd_name)
            if resolved:
                res_norm = os.path.normcase(os.path.abspath(resolved))
                if res_norm == target_norm:
                    add_dep(EnvironmentDependency(
                        variable_name="PATH",
                        matched_path=resolved,
                        source="Active PATH Lookup",
                        match_type="PATH_EXECUTABLE",
                        category="ACTIVE_DEPENDENCY",
                        risk_level=RiskLevel.HIGH,
                        confidence=ConfidenceLevel.CONFIRMED,
                        description=f"Executing '{cmd_name}' currently resolves directly to this file.",
                        why_it_matters=f"Invoking command '{cmd_name}' from terminal will fail if this file is deleted.",
                        raw_value=resolved,
                    ))

    # ── Helper Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def _get_var_case_insensitive(d: Dict[str, str], key: str) -> Optional[str]:
        """Look up a variable case-insensitively in an environment dict."""
        key_upper = key.upper()
        for k, v in d.items():
            if k.upper() == key_upper:
                return v
        return None

    def _is_active_runtime_path(self, target_norm: str) -> bool:
        """Check if target matches the active Python prefix, virtualenv, or conda env."""
        # Current python executable or sys.prefix
        try:
            curr_prefix = os.path.normcase(os.path.abspath(sys.prefix))
            if target_norm == curr_prefix or curr_prefix.startswith(target_norm + os.sep):
                return True
        except Exception:
            pass

        # CONDA_PREFIX
        conda_p = self.process_env.get("CONDA_PREFIX")
        if conda_p:
            try:
                c_norm = os.path.normcase(os.path.abspath(conda_p))
                if target_norm == c_norm or c_norm.startswith(target_norm + os.sep):
                    return True
            except Exception:
                pass

        # VIRTUAL_ENV
        venv = self.process_env.get("VIRTUAL_ENV")
        if venv:
            try:
                v_norm = os.path.normcase(os.path.abspath(venv))
                if target_norm == v_norm or v_norm.startswith(target_norm + os.sep):
                    return True
            except Exception:
                pass

        return False

    def _is_active_runtime_var(self, var_name: str, target_norm: str) -> bool:
        """Check if a tool variable is actively bound in the current session."""
        if var_name in ("CONDA_PREFIX", "VIRTUAL_ENV"):
            return self._is_active_runtime_path(target_norm)
        return False
