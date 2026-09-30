"""
ML Project Demo - app.py
A simple ML application that demonstrates file dependencies.
Used as the test project for PreView AI.
"""
import pickle
import json
import pandas as pd

# Load configuration
with open("config.json", "r") as f:
    config = json.load(f)

# Load the trained model
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

# Read the dataset
data = pd.read_csv("dataset.csv")

# Make predictions
print(f"Model type: {type(model).__name__}")
print(f"Dataset shape: {data.shape}")
print(f"Config: {config}")

predictions = model.predict(data[["feature1", "feature2"]])
print(f"Predictions: {predictions[:5]}")
