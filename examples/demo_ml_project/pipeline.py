"""
pipeline.py — Demo ML Pipeline Orchestrator
Depends on train.py and evaluate.py (which in turn depend on dataset.csv).
Creates a deeper dependency chain for acceptance test coverage.
Used for PreView AI acceptance tests.
"""
import subprocess
import sys
import json

# ── References to sibling modules and data ─────────────────────────────────────
TRAIN_SCRIPT = "train.py"
EVALUATE_SCRIPT = "evaluate.py"
CONFIG_PATH = "config.json"
DATASET_PATH = "dataset.csv"


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def run_step(script: str, description: str):
    print(f"\n[PIPELINE] Running {description}: {script}")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] {description} failed:\n{result.stderr}")
        return False
    print(result.stdout)
    return True


def main():
    print("[PIPELINE] Starting ML pipeline...")
    config = load_config(CONFIG_PATH)
    print(f"[PIPELINE] Using dataset: {config.get('data_path', DATASET_PATH)}")

    if not run_step(TRAIN_SCRIPT, "Training"):
        print("[PIPELINE] Pipeline aborted at training step.")
        return

    if not run_step(EVALUATE_SCRIPT, "Evaluation"):
        print("[PIPELINE] Pipeline aborted at evaluation step.")
        return

    print("\n[PIPELINE] Pipeline complete.")


if __name__ == "__main__":
    main()
