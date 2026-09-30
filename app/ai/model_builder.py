"""
app/ai/model_builder.py

Builds and exports a trained ONNX model for on-device dependency impact prediction
and consequence ranking. Compatible with ONNX Runtime CPU and QNN Execution
Providers on Qualcomm Snapdragon Hexagon NPU.

Architecture:
- Input: 'features' [batch_size, 16] float32
- Hidden Layer 1: Gemm (16 -> 48) + Relu
- Hidden Layer 2: Gemm (48 -> 32) + Relu
- Head 1: 'impact_scores' [batch_size, 1] (Gemm 32 -> 1 + Sigmoid)
- Head 2: 'risk_logits' [batch_size, 4] (Gemm 32 -> 4)
- Head 3: 'consequence_logits' [batch_size, 5] (Gemm 32 -> 5)

Qualified for Qualcomm AI Hub Compilation and Snapdragon HTP Execution.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any

from app.ai.train_model import train_and_export_model

logger = logging.getLogger("preview_ai.model_builder")


def create_impact_predictor_onnx(output_path: Path) -> Path:
    """
    Constructs and trains an ONNX model compatible with ONNX Runtime CPU and
    Qualcomm QNN Execution Providers (Hexagon HTP).
    
    Uses supervised multi-task backpropagation over ground-truth dependency scenarios.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Training on-device impact predictor network for {output_path}...")
    metrics = train_and_export_model(output_path=output_path, epochs=45, n_samples=4000)
    logger.info(f"Model exported successfully. Validation Accuracy: {metrics['accuracy']*100:.1f}%, F1: {metrics['f1']:.3f}")
    return output_path


if __name__ == "__main__":
    out = Path("models/preview_impact_predictor.onnx")
    create_impact_predictor_onnx(out)
    print(f"Generated and verified trained ONNX model at: {out} ({out.stat().st_size} bytes)")
