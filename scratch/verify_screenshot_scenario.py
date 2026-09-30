"""
scratch/verify_screenshot_scenario.py

Tests the exact screenshot scenario:
Target: C:\\Users\\sai\\anaconda3
Environment has:
  PATH contains C:\\Users\\sai\\anaconda3 and C:\\Users\\sai\\anaconda3\\Scripts
Tests what PreView AI concludes and what evidence it finds.
"""
from app.consequence.environment_analyzer import EnvironmentDependencyAnalyzer
from app.consequence.analyzer import ConsequenceAnalyzer
from app.graph.builder import StateGraph
from app.ai.explanation import ExplanationEngine
from app.graph.models import StructuredAction

def run():
    target = r"C:\Users\sai\anaconda3"
    print(f"Target: {target}")

    # Set up analyzer with the scenario's Windows User PATH
    env_analyzer = EnvironmentDependencyAnalyzer(
        system_env={"PATH": r"C:\Windows\system32;C:\Windows"},
        user_env={"PATH": r"C:\Users\sai\anaconda3;C:\Users\sai\anaconda3\Scripts"},
        env={},
    )

    graph = StateGraph()
    consequence_analyzer = ConsequenceAnalyzer(graph, env_analyzer=env_analyzer)
    impact = consequence_analyzer.compute_impact(target, "DELETE")

    print(f"\n--- IMPACT ASSESSMENT ---")
    print(f"Risk Level: {impact.risk.value}")
    print(f"Summary: {impact.summary}")
    print(f"Environment Dependencies Count: {len(impact.environment_dependencies)}")
    print(f"Project Affected Files Count: {len(impact.affected_files)}")

    print(f"\n--- DETECTED EVIDENCE ---")
    for dep in impact.environment_dependencies:
        print(f"• Name: {dep.name}")
        print(f"  Path: {dep.path}")
        print(f"  Relationship: {dep.relationship}")
        print(f"  Risk: {dep.risk_level.value}")
        print(f"  Confidence: {dep.confidence.value}")
        print(f"  Description: {dep.description}")
        print(f"  Evidence Summary: {dep.evidence_summary}")
        for ev in dep.evidence_chain:
            print(f"  Evidence Chain: {ev.raw_text}")
        print()

    # Generate explanation via ExplanationEngine
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
    print("--- EXPLANATION ENGINE OUTPUT ---")
    print(explanation)

if __name__ == "__main__":
    run()
