"""Rebuild the ONNX model with corrected metadata."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from app.ai.model_builder import create_impact_predictor_onnx
out = Path("models/preview_impact_predictor.onnx")
create_impact_predictor_onnx(out)
print(f"Model rebuilt: {out} ({out.stat().st_size} bytes)")
