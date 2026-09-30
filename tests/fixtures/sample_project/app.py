"""
Sample application for testing PreView AI dependency graph.
"""
import os
import json
import utils

CONFIG_PATH = "config.json"
DATASET_PATH = "dataset.csv"
MODEL_PATH = "model.pkl"

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def load_model():
    import pickle
    with open("model.pkl", "rb") as f:
        return pickle.load(f)

def run():
    config = load_config()
    model = load_model()
    print("Running with config:", config)
    utils.process_data("dataset.csv", "model.pkl")

if __name__ == "__main__":
    run()
