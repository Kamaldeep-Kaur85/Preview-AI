"""
benchmarks/benchmark_pipeline.py

Performance and Accuracy Benchmark Harness for PreView AI.
Implements the experimental methodology outlined in README.md:
- Section 28: Experimental Methodology (Graph build time, simulation latency, consequence analysis)
- Section 29: Statistical Rigor (repeated runs, median, spread, memory)
- Section 30: Baseline Comparison (Baseline A: string match, Baseline B: direct refs, Full PreView AI)
- Section 53: Team Checklist Performance metrics
"""
import sys
import time
import statistics
import tracemalloc
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.builder import GraphBuilder
from app.graph.models import StructuredAction
from app.simulation.simulator import Simulator
from app.consequence.analyzer import ConsequenceAnalyzer
from app.safety.policy import SafetyPolicy


def run_performance_benchmarks(project_dir: Path, iterations: int = 15):
    print("=" * 70)
    print(f" PreView AI Performance Benchmark — {project_dir.name}")
    print(f" Iterations: {iterations} | Python: {sys.version.split()[0]}")
    print("=" * 70)

    graph_times = []
    sim_times = []
    analysis_times = []

    action = StructuredAction(
        operation="DELETE",
        target="dataset.csv",
        raw_intent="Delete dataset.csv",
    )

    tracemalloc.start()
    mem_before, _ = tracemalloc.get_traced_memory()

    # Pre-build to test warm vs cold
    builder = GraphBuilder(project_root=project_dir)
    initial_graph = builder.build()
    print(f"Graph initialized: {initial_graph.node_count} nodes, {initial_graph.edge_count} edges.\n")

    for i in range(iterations):
        # 1. Graph building
        t0 = time.perf_counter()
        b = GraphBuilder(project_root=project_dir)
        g = b.build()
        t1 = time.perf_counter()
        graph_times.append((t1 - t0) * 1000)

        # 2. Simulation
        sim = Simulator(g)
        t2 = time.perf_counter()
        sim_res = sim.simulate(action)
        t3 = time.perf_counter()
        sim_times.append((t3 - t2) * 1000)

        # 3. Consequence Analysis
        analyzer = ConsequenceAnalyzer(g)
        t4 = time.perf_counter()
        analysis = analyzer.analyze(sim_res)
        t5 = time.perf_counter()
        analysis_times.append((t5 - t4) * 1000)

    mem_current, mem_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    def stats(data):
        return {
            "median": statistics.median(data),
            "mean": statistics.mean(data),
            "min": min(data),
            "max": max(data),
            "stdev": statistics.stdev(data) if len(data) > 1 else 0.0,
        }

    g_stat = stats(graph_times)
    s_stat = stats(sim_times)
    a_stat = stats(analysis_times)

    print(f"{'Component':<26} | {'Median (ms)':<12} | {'Mean (ms)':<12} | {'Min - Max (ms)':<15} | {'StdDev':<8}")
    print("-" * 82)
    print(f"{'1. Graph Builder':<26} | {g_stat['median']:>10.2f} ms | {g_stat['mean']:>10.2f} ms | {g_stat['min']:>6.2f} - {g_stat['max']:<6.2f} | {g_stat['stdev']:>6.2f}")
    print(f"{'2. Virtual Simulator':<26} | {s_stat['median']:>10.2f} ms | {s_stat['mean']:>10.2f} ms | {s_stat['min']:>6.2f} - {s_stat['max']:<6.2f} | {s_stat['stdev']:>6.2f}")
    print(f"{'3. Consequence Engine':<26} | {a_stat['median']:>10.2f} ms | {a_stat['mean']:>10.2f} ms | {a_stat['min']:>6.2f} - {a_stat['max']:<6.2f} | {a_stat['stdev']:>6.2f}")
    print("-" * 82)
    print(f"Memory Allocated: {(mem_current - mem_before) / (1024 * 1024):.2f} MB | Peak: {mem_peak / (1024 * 1024):.2f} MB\n")


def run_baseline_comparison(project_dir: Path):
    print("=" * 70)
    print(f" PreView AI vs Baseline Comparison — Target: dataset.csv")
    print("=" * 70)

    target_name = "dataset.csv"

    # Baseline A: Naive filename/string matching across all text files
    files = list(project_dir.rglob("*"))
    matches_baseline_a = []
    for f in files:
        if f.is_file() and f.suffix in (".py", ".json", ".md", ".txt"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if target_name in content and f.name != target_name:
                    matches_baseline_a.append(f.name)
            except Exception:
                pass

    # Baseline B: Direct AST references only (single-hop)
    builder = GraphBuilder(project_root=project_dir)
    graph = builder.build()
    direct_dependents = []
    for node_id, node in graph.nodes.items():
        if node.name == target_name:
            deps = graph.get_dependents(node_id)
            direct_dependents = [d.name for _, d in deps]
            break

    # Full PreView AI: Simulation + Impact Propagation + Transitive Downstream
    action = StructuredAction(operation="DELETE", target=target_name)
    sim = Simulator(graph)
    sim_res = sim.simulate(action)
    analyzer = ConsequenceAnalyzer(graph)
    analysis = analyzer.analyze(sim_res)

    preview_affected = [item.affected_node_name for item in analysis.all_consequences]

    print(f"{'Approach':<35} | {'Detected Dependents':<20} | {'Transitive Chains?':<18}")
    print("-" * 79)
    print(f"{'Baseline A (String match)':<35} | {len(matches_baseline_a):<20} | {'No (naive)':<18}")
    print(f"{'Baseline B (Direct AST static)':<35} | {len(direct_dependents):<20} | {'No (1-hop only)':<18}")
    print(f"{'PreView AI (Graph + Consequence)':<35} | {len(preview_affected):<20} | {'Yes (multi-hop)':<18}")
    print("-" * 79)
    print(f"PreView AI Detected Files: {preview_affected}")
    print(f"Overall Assessed Risk: {analysis.overall_risk.value}\n")


if __name__ == "__main__":
    demo_dir = PROJECT_ROOT / "examples" / "demo_ml_project"
    if not demo_dir.exists():
        demo_dir = PROJECT_ROOT / "tests" / "fixtures" / "sample_project"

    run_performance_benchmarks(demo_dir, iterations=20)
    run_baseline_comparison(demo_dir)
