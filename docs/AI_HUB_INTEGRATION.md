# PreView AI — Qualcomm AI Hub Integration

> **Status Key**: IMPLEMENTED = code exists | VERIFIED = confirmed working | NOT VERIFIED = requires Snapdragon hardware + API token

---

## 1. Overview

PreView AI uses a **custom-trained ONNX model** (`preview_impact_predictor.onnx`) that is technically qualified for Qualcomm AI Hub compilation and Snapdragon Hexagon HTP execution.

The model is **not** sourced from the Qualcomm AI Hub Model Zoo. It was trained locally on synthetic software dependency data via `app/ai/train_model.py`.

Integration chain:

| Step | Status |
|:---|:---|
| Custom-trained ONNX model | **VERIFIED** (12.3 KB, Opset 17) |
| HTP operator compliance check | **IMPLEMENTED + VERIFIED** (all 8 nodes pass) |
| QNN Execution Provider configuration | **IMPLEMENTED** (`QNNBackend` in `backend.py`) |
| QNN provider activated at runtime | **NOT VERIFIED** (requires Snapdragon X Elite / Plus) |
| AI Hub compile job (live) | **NOT VERIFIED** (requires `qai_hub` SDK + API token) |
| AI Hub profile job (live) | **NOT VERIFIED** (same) |
| NPU inference measured | **NOT TESTED** |

For the full verified status audit, see [`SNAPDRAGON_AI.md`](SNAPDRAGON_AI.md).

---

## 2. Model Specifications

**Model**: `preview_impact_predictor.onnx`

| Field | Value | Status |
|:---|:---|:---|
| Architecture | Multi-Head MLP (16→48→32, 3 heads) | VERIFIED |
| Training | Supervised multi-task Adam backpropagation on synthetic data | VERIFIED |
| ONNX Opset | Opset 17, IR version 9 | VERIFIED |
| Model Disk Size | 12.3 KB | VERIFIED |
| Operator Coverage | 8 nodes: Gemm×5, Relu×2, Sigmoid×1 | VERIFIED |
| Hexagon HTP compatibility | All operators in HTP-supported set | VERIFIED by code |
| CPU fallback | `CPUExecutionProvider` | VERIFIED — confirmed operational |
| QNN acceleration | `QNNExecutionProvider` | IMPLEMENTED — not verified on hardware |

---

## 3. HTP Operator Delegation

| Operator | Count | Hexagon HTP Unit | Delegation Status |
|:---|:---|:---|:---|
| `Gemm` | 5 | Matrix Compute Engine | 100% (on Snapdragon hardware) |
| `Relu` | 2 | Vector Engine | 100% (on Snapdragon hardware) |
| `Sigmoid` | 1 | Activation LUT | 100% (on Snapdragon hardware) |
| **Total** | **8** | **Qualcomm Hexagon NPU** | **Configured — requires hardware verification** |

---

## 4. Compilation + Profiling Workflow

### When `qai_hub` SDK is NOT installed (current dev environment)

The `AIHubManager` operates in offline qualification mode:
- `verify_model_compliance()` runs locally (no network), checks opset and operator coverage
- `compile_model()` returns an **offline qualification receipt** with estimated values
- `profile_on_snapdragon_device()` returns **estimated performance numbers** (not measured)

### When `qai_hub` SDK IS installed + API token configured

```bash
# 1. Install Qualcomm AI Hub SDK
pip install qai-hub

# 2. Configure API token
qai-hub configure --api_token <YOUR_TOKEN>

# 3. Submit compilation for Snapdragon X Elite
qai-hub compile \
    --model models/preview_impact_predictor.onnx \
    --device "Snapdragon X Elite CRD" \
    --options "--target_runtime qnn_lib_aarch64_android"

# 4. Profile on real Snapdragon hardware
qai-hub profile \
    --model models/preview_impact_predictor.onnx \
    --device "Snapdragon X Elite CRD"
```

### Running the local compliance check (no hardware required)

```bash
python -m app.ai.ai_hub_manager
```

---

## 5. CPU Fallback (Verified)

On non-Snapdragon machines (Intel / AMD x64), PreView AI automatically:
1. Detects the processor name and confirms absence of Snapdragon / Qualcomm signatures
2. Confirms `QNNExecutionProvider` is not in `ort.get_available_providers()`
3. Instantiates `CPUBackend` → `CPUExecutionProvider`
4. UI badge displays: `● ONNX Runtime • CPU`
5. Diagnostics report: `Snapdragon Hardware: Not detected (x86/x64 dev environment)`

This behavior has been verified operational on Intel Core i7-10610U.

---

## 6. AI Hub Model Zoo (Planned)

MobileBERT / DistilBERT from the Qualcomm AI Hub Model Zoo for conversational intent parsing is **future planned work**, not a currently implemented feature. Current intent parsing uses local heuristic-based parsing in `app/ai/intent_parser.py`.

---

## 7. Verification Commands

```bash
# Verify model compliance (no hardware needed)
python -m app.ai.ai_hub_manager

# Run CPU benchmark
python -m app.benchmark

# Run model evaluation
python -m app.evaluation

# Check active backend at startup
python -m app.main --diagnostics
```
