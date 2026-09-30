"""
tests/unit/test_environment_dependency_analyzer.py

Unit tests for EnvironmentDependencyAnalyzer and its integration with ConsequenceAnalyzer:
  - PATH references target directory
  - PATH does not reference target
  - parent-directory match
  - User vs System PATH
  - unrelated environment variable
  - no false positive (.android, .anaconda)
  - deleted target referenced by environment variable
  - active runtime dependency (HIGH)
  - critical system dependency (CRITICAL)
  - consequence analyzer integration & explanation evidence
"""
import os
from pathlib import Path
import pytest

from app.consequence.environment_analyzer import (
    EnvironmentDependencyAnalyzer,
    EnvironmentDependency,
)
from app.consequence.analyzer import ConsequenceAnalyzer
from app.graph.builder import StateGraph
from app.graph.models import ConfidenceLevel, RiskLevel, StructuredAction
from app.ai.explanation import ExplanationEngine


def test_path_references_target_directory():
    """Requirement: PATH references target directory -> exact match detected with evidence."""
    target = r"C:\Tools\MyTool"
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": r"C:\Windows\system32;C:\Tools\MyTool;C:\Other"},
        user_env={},
        env={},
    )
    deps = analyzer.analyze_target(target)
    assert len(deps) == 1
    dep = deps[0]
    assert dep.variable_name == "PATH"
    assert dep.source == "System PATH"
    assert dep.match_type == "EXACT"
    assert dep.category == "CONFIGURATION_REFERENCE"
    assert dep.risk_level == RiskLevel.MEDIUM
    assert dep.confidence == ConfidenceLevel.CONFIRMED
    assert "MyTool" in dep.description
    assert "relying on" in dep.why_it_matters.lower() or "binaries" in dep.why_it_matters.lower()


def test_path_does_not_reference_target():
    """Requirement: PATH does not reference target -> no dependencies detected."""
    target = r"C:\Users\sai\Projects\StandaloneApp"
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": r"C:\Windows;C:\Windows\system32"},
        user_env={"PATH": r"C:\Users\sai\AppData\Local\Programs\Python"},
        env={},
    )
    deps = analyzer.analyze_target(target)
    assert len(deps) == 0


def test_parent_directory_match():
    """Requirement: Parent directory match -> deleting parent will break configured child entries."""
    target = r"C:\Users\sai\anaconda3"
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={},
        user_env={"PATH": r"C:\Users\sai\anaconda3\Scripts;C:\Users\sai\anaconda3\Library\bin;C:\Windows"},
        env={},
    )
    deps = analyzer.analyze_target(target)
    # Should detect the child entries configured in PATH
    assert len(deps) >= 2
    matched_paths = [d.matched_path for d in deps]
    assert any("Scripts" in p for p in matched_paths)
    assert any("Library" in p for p in matched_paths)
    for dep in deps:
        assert dep.match_type == "PARENT_DIRECTORY"
        assert dep.source == "User PATH"
        assert dep.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
        assert "deleting this directory will delete configured path entry" in dep.why_it_matters.lower() or "break" in dep.why_it_matters.lower()


def test_user_vs_system_path():
    """Requirement: User vs System PATH distinguished with exact source attribution."""
    sys_dir = r"C:\Program Files\Java\jdk-17\bin"
    usr_dir = r"C:\Users\sai\AppData\Local\CustomBin"

    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": sys_dir},
        user_env={"PATH": usr_dir},
        env={},
    )

    sys_deps = analyzer.analyze_target(sys_dir)
    assert len(sys_deps) == 1
    assert sys_deps[0].source == "System PATH"

    usr_deps = analyzer.analyze_target(usr_dir)
    assert len(usr_deps) == 1
    assert usr_deps[0].source == "User PATH"


def test_unrelated_environment_variable():
    """Requirement: Unrelated environment variables do not cause false dependencies."""
    target = r"C:\Users\sai\anaconda3"
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={
            "OS": "Windows_NT",
            "PROCESSOR_ARCHITECTURE": "AMD64",
            "NUMBER_OF_PROCESSORS": "8",
        },
        user_env={
            "THEME": "dark",
            "TEMP": r"C:\Users\sai\AppData\Local\Temp",
            "RANDOM_SETTING": "enabled",
        },
        env={
            "PROMPT": "$P$G",
        },
    )
    deps = analyzer.analyze_target(target)
    assert len(deps) == 0


def test_no_false_positive():
    """
    Requirement: Do NOT classify .android or .anaconda as HIGH merely because
    Android Studio or Anaconda exists. Distinguish software existence from active env reference.
    """
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": r"C:\Windows\system32"},
        user_env={
            "ANDROID_HOME": r"C:\Users\sai\AppData\Local\Android\Sdk",
            "PATH": r"C:\Users\sai\AppData\Local\Android\Sdk\platform-tools",
        },
        env={},
    )

    # .android is user home config/cache folder (NOT ANDROID_HOME SDK)
    target_android = r"C:\Users\sai\.android"
    deps_android = analyzer.analyze_target(target_android)
    assert len(deps_android) == 0  # No false positive!

    # When analyzed through ConsequenceAnalyzer, .android is LOW (cache/config only), NOT HIGH
    graph = StateGraph()
    consequence_analyzer = ConsequenceAnalyzer(graph, env_analyzer=analyzer)
    impact_android = consequence_analyzer.compute_impact(target_android, "DELETE")
    assert impact_android.risk == RiskLevel.LOW
    assert len(impact_android.environment_dependencies) == 0
    assert "configuration/cache" in impact_android.summary.lower()

    # Similarly for .anaconda
    target_anaconda_conf = r"C:\Users\sai\.anaconda"
    deps_anac = analyzer.analyze_target(target_anaconda_conf)
    assert len(deps_anac) == 0
    impact_anac = consequence_analyzer.compute_impact(target_anaconda_conf, "DELETE")
    assert impact_anac.risk == RiskLevel.LOW


def test_deleted_target_referenced_by_environment_variable():
    """
    Requirement: Deleted/non-existent target referenced by environment variable.
    Even if the folder was already deleted on disk, environment reference is still detected.
    """
    deleted_path = r"C:\NonExistent\DeletedTool\bin"
    assert not Path(deleted_path).exists()

    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": f"C:\\Windows;{deleted_path};C:\\System"},
        user_env={},
        env={},
    )
    deps = analyzer.analyze_target(deleted_path)
    assert len(deps) == 1
    assert deps[0].variable_name == "PATH"
    assert deps[0].matched_path.lower() == deleted_path.lower()
    assert deps[0].source == "System PATH"

    # Consequence analysis detects environment reference even for missing folder
    graph = StateGraph()
    consequence_analyzer = ConsequenceAnalyzer(graph, env_analyzer=analyzer)
    impact = consequence_analyzer.compute_impact(deleted_path, "DELETE")
    assert len(impact.environment_dependencies) == 1
    assert impact.risk == RiskLevel.MEDIUM
    assert "environment dependency detected" in impact.summary.lower()


def test_consequence_analyzer_anaconda_scenario():
    """
    Requirement 9: Exact scenario from prompt.
    PATH contains:
      C:\\Users\\sai\\anaconda3
      C:\\Users\\sai\\anaconda3\\Scripts
    Preview deletion of anaconda3 installation:
    PreView AI detects PATH dependency, sets risk to MEDIUM (or HIGH if active),
    and warns that commands relying on those entries may stop resolving.
    """
    target = r"C:\Users\sai\anaconda3"
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={},
        user_env={"PATH": r"C:\Users\sai\anaconda3;C:\Users\sai\anaconda3\Scripts"},
        env={},
    )

    graph = StateGraph()
    consequence_analyzer = ConsequenceAnalyzer(graph, env_analyzer=analyzer)
    impact = consequence_analyzer.compute_impact(target, "DELETE")

    # 1. Separate category: ENVIRONMENT_DEPENDENCY
    assert len(impact.environment_dependencies) >= 2
    for env_dep in impact.environment_dependencies:
        assert env_dep.impact_type == "ENVIRONMENT_DEPENDENCY"
        assert env_dep.confidence == ConfidenceLevel.CONFIRMED

    # 2. Project dependencies remain separate
    assert len(impact.affected_files) == 0

    # 3. Risk level is at least MEDIUM (not falsely SAFE)
    assert impact.risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)

    # 4. Summary and explanation are evidence-backed
    assert "PATH" in impact.summary
    assert "anaconda3" in impact.summary

    # 5. ExplanationEngine formats clear evidence
    action = StructuredAction(operation="DELETE", target=target, raw_intent=f"delete {target}")
    from app.consequence.analyzer import ConsequenceAnalysis
    analysis = ConsequenceAnalysis(
        action=action,
        direct=[consequence_analyzer._impact_to_consequence(f) for f in impact.direct_impacts],
        dependency=[],
        environment=[consequence_analyzer._impact_to_consequence(f) for f in impact.environment_dependencies],
        secondary=[],
        uncertain=[],
        overall_risk=impact.risk,
        impact_result=impact,
    )
    engine = ExplanationEngine()
    explanation = engine.explain(analysis)
    assert "Environment Dependency Impact" in explanation
    assert "PATH" in explanation
    assert "references this directory" in explanation.lower() or "configured" in explanation.lower()
    assert "android studio" not in explanation.lower()  # Never invent unrelated application!


def test_tool_variables_java_and_android():
    """Test explicit inspection of JAVA_HOME, ANDROID_HOME, and ANDROID_SDK_ROOT."""
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"JAVA_HOME": r"C:\Program Files\Java\jdk-17"},
        user_env={"ANDROID_HOME": r"C:\Android\Sdk", "ANDROID_SDK_ROOT": r"C:\Android\Sdk"},
        env={},
    )

    # JAVA_HOME target
    deps_java = analyzer.analyze_target(r"C:\Program Files\Java\jdk-17")
    assert len(deps_java) == 1
    assert deps_java[0].variable_name == "JAVA_HOME"
    assert deps_java[0].source == "System"

    # ANDROID_HOME target
    deps_android = analyzer.analyze_target(r"C:\Android\Sdk")
    assert len(deps_android) == 2
    var_names = {d.variable_name for d in deps_android}
    assert "ANDROID_HOME" in var_names
    assert "ANDROID_SDK_ROOT" in var_names


def test_critical_system_dependency():
    """Requirement: Critical system dependency -> CRITICAL risk level."""
    graph = StateGraph()
    analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": r"C:\Windows\System32;C:\Windows"},
        user_env={},
        env={},
    )
    consequence_analyzer = ConsequenceAnalyzer(graph, env_analyzer=analyzer)
    impact = consequence_analyzer.compute_impact(r"C:\Windows\System32", "DELETE")
    assert impact.risk == RiskLevel.CRITICAL
