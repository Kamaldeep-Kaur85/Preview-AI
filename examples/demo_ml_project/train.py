"""
train.py — Demo ML Training Script
This file intentionally references dataset.csv to create a detectable dependency.
Used for PreView AI acceptance tests.
"""
import csv
import json
import os
import pickle
import random

# ── Configuration ──────────────────────────────────────────────────────────────
CONFIG_PATH = "config.json"
DATASET_PATH = "dataset.csv"
MODEL_OUTPUT = "model.pkl"


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_dataset(path: str) -> list:
    """Load training data from dataset.csv"""
    rows = []
    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            rows.append(row)
    return rows


def train_model(data: list) -> dict:
    """Simulate model training on the loaded dataset."""
    print(f"Training on {len(data)} samples from {DATASET_PATH} ...")
    # Dummy model: just stores the mean of feature1
    feature1_vals = []
    for row in data:
        try:
            feature1_vals.append(float(row.get("feature1", 0)))
        except ValueError:
            pass
    mean_f1 = sum(feature1_vals) / len(feature1_vals) if feature1_vals else 0.0
    model = {"type": "DummyClassifier", "mean_feature1": mean_f1, "n_samples": len(data)}
    return model


def save_model(model: dict, path: str):
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"Model saved to {path}")


def main():
    config = load_config(CONFIG_PATH)
    print(f"Config: {config}")

    dataset_file = config.get("data_path", DATASET_PATH)
    data = load_dataset(dataset_file)
    model = train_model(data)
    save_model(model, MODEL_OUTPUT)
    print("Training complete.")


if __name__ == "__main__":
    main()
