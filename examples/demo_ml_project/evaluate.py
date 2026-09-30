"""
evaluate.py — Demo ML Evaluation Script
This file intentionally references dataset.csv and model.pkl to create detectable dependencies.
Used for PreView AI acceptance tests.
"""
import csv
import json
import pickle

# ── Paths referenced explicitly ────────────────────────────────────────────────
CONFIG_PATH = "config.json"
DATASET_PATH = "dataset.csv"
MODEL_PATH = "model.pkl"


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_dataset(path: str) -> list:
    """Load evaluation data from dataset.csv"""
    rows = []
    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            rows.append(row)
    return rows


def load_model(path: str) -> dict:
    """Load trained model from model.pkl"""
    with open(path, "rb") as f:
        return pickle.load(f)


def evaluate(model: dict, data: list) -> dict:
    """Evaluate model on dataset."""
    print(f"Evaluating {len(data)} samples from {DATASET_PATH} ...")
    correct = 0
    for row in data:
        try:
            label = int(float(row.get("label", 0)))
            pred = 1 if float(row.get("feature1", 0)) > model.get("mean_feature1", 0) else 0
            if pred == label:
                correct += 1
        except (ValueError, TypeError):
            pass
    accuracy = correct / len(data) if data else 0.0
    return {"accuracy": accuracy, "n_samples": len(data)}


def main():
    config = load_config(CONFIG_PATH)
    dataset_file = config.get("data_path", DATASET_PATH)
    model_file = config.get("model_path", MODEL_PATH)

    data = load_dataset(dataset_file)
    model = load_model(model_file)
    results = evaluate(model, data)
    print(f"Evaluation results: {results}")


if __name__ == "__main__":
    main()
