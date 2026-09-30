# PreView AI — Snapdragon / QNN Integration: Verified Status

> **Audit date**: 2026-09-30  
> **Principle**: Claims must match reality. Implementation ≠ execution. Configuration ≠ measurement.

---

## 1. Verification Table

| Layer | Status | Evidence |
|:---|:---|:---|
| ONNX model present | **VERIFIED** | `models/preview_impact_predictor.onnx` (12.3 KB) exists |
| ONNX Runtime used | **VERIFIED** | `app/ai/backend.py` — `onnxruntime.InferenceSession` |
| QNN Execution Provider configured | **IMPLEMENTED** | `QNNBackend` class in `backend.py` configures `QNNExecutionProvider` with `QnnHtp.dll` |
| QNN provider actually loaded | **NOT VERIFIED** | No Snapdragon hardware available for testing |
| HTP backend delegation | **NOT VERIFIED** | Cannot verify without Snapdragon hardware |
| Snapdragon hardware present | **NOT VERIFIED** | Dev machine: Intel Core i7-10610U (AMD64) |
| NPU execution confirmed | **NOT TESTED** | Requires Snapdragon X Elite / Plus + QNN SDK ≥ v2.20 |
| CPU fallback path | **VERIFIED** | `CPUBackend` executes correctly; confirmed via `python -m app.benchmark` |
| AI Hub model download | **NOT PRESENT** | Model is custom-trained locally; not downloaded from AI Hub |
| AI Hub compile job (live) | **NOT VERIFIED** | Requires `qai_hub` SDK + valid `QAI_HUB_API_TOKEN`; absent |
| AI Hub profile job (live) | **NOT VERIFIED** | Same as above |

---

## 2. Model Origin Chain

```
MODEL SOURCE
    Custom-trained — train_model.py generates model from synthetic data
    Status: IMPLEMENTED + VERIFIED
    ↓
MODEL ARTIFACT
    preview_impact_predictor.onnx (ONNX Opset 17, IR v9, FP32, 12.3 KB)
    Status: VERIFIED (file present, loads correctly)
    ↓
OPTIMIZATION / COMPILATION
    All 8 ONNX nodes use Hexagon HTP-compatible operators (Gemm, Relu, Sigmoid)
    Qualification check: IMPLEMENTED (ai_hub_manager.verify_model_compliance())
    Actual AI Hub compile job: NOT VERIFIED (requires API token + Snapdragon target)
    ↓
RUNTIME
    ONNX Runtime ≥ 1.18.0 with automatic provider selection
    CPU path: VERIFIED (measured on Intel i7-10610U)
    QNN path: IMPLEMENTED, NOT VERIFIED on actual hardware
    ↓
INFERENCE
    CPU inference: VERIFIED
    NPU inference: NOT TESTED — no Snapdragon hardware in current environment
```

---

## 3. What Is Verified

### CPU Inference (Dev Machine)

Measured on `Intel(R) Core(TM) i7-10610U CPU @ 1.80GHz`, AMD64, Windows 11:

| Metric | Measured Value |
|:---|:---|
| P50 Inference Latency | ~0.10–0.14 ms |
| Throughput | ~32,000–34,000 inf/sec |
| Backend | `CPUExecutionProvider` |
| Offline | Yes |

> **Source**: `docs/SNAPDRAGON_BENCHMARK.md` Section 2 (Local Host Run)

### QNN Provider Code (Implemented)

`QNNBackend.load()` correctly configures `QNNExecutionProvider` with:
- `backend_path`: `QnnHtp.dll`
- `htp_performance_mode`: `burst`
- `htp_graph_finalization_optimization_mode`: `3`

This code will function on a Snapdragon device with QNN SDK ≥ v2.20 installed.

### Model HTP Operator Compliance (Verified by Code Analysis)

All 8 ONNX nodes use HTP-accelerated operators — 0 would fall back to CPU on Snapdragon hardware.

---

## 4. What Is NOT Verified

### Snapdragon Hardware Execution

**Snapdragon hardware execution could not be independently verified in the current environment.**

No Snapdragon X Elite / Plus hardware or QNN SDK was available for testing.

### AI Hub Offline Receipt (Not Real Measurement)

`ai_hub_manager.compile_model()` and `profile_on_snapdragon_device()` fall back to **hardcoded offline receipt objects** when no live `qai_hub` SDK + API token is present. These contain:
- Fabricated job IDs (e.g., `qai-hub-job-sc8380xp-<timestamp>`)
- Hardcoded latency values (0.342 ms, 12,840 inf/sec, 1.42 MB)
- A `dashboard_url` that points to a URL not verified to exist

These are **code-level placeholders**, not measured results.

### Numbers Requiring Hardware Verification

| Claim | Status |
|:---|:---|
| 0.342 ms P50 on Hexagon NPU | NOT INDEPENDENTLY VERIFIED |
| 14.20 ms model load on NPU | NOT INDEPENDENTLY VERIFIED |
| 12,840 inf/sec (NPU) | NOT INDEPENDENTLY VERIFIED |
| 1.42 MB NPU memory | NOT INDEPENDENTLY VERIFIED |
| 4.74× speedup | NOT INDEPENDENTLY VERIFIED |

### AI Hub Model Zoo (Planned, Not Implemented)

MobileBERT / DistilBERT from AI Hub for intent parsing is **future planned work**. Current intent parsing uses `app/ai/intent_parser.py` with local heuristics.

---

## 5. AI Hub–Ready Status

The model is technically qualified for AI Hub compilation:
- ONNX Opset 17 ✓
- All operators in Hexagon HTP primitive set ✓
- FP32 (INT8/FP16 quantization-ready) ✓
- 12.3 KB (well within upload limits) ✓

To compile and profile on real hardware:

```bash
pip install qai-hub
qai-hub configure --api_token <YOUR_TOKEN>
qai-hub compile \
    --model models/preview_impact_predictor.onnx \
    --device "Snapdragon X Elite CRD" \
    --options "--target_runtime qnn_lib_aarch64_android"
qai-hub profile \
    --model models/preview_impact_predictor.onnx \
    --device "Snapdragon X Elite CRD"
```

---

## 6. Corrected Claim Vocabulary

| Instead of… | Use… |
|:---|:---|
| "Verified on Snapdragon hardware" | "Configured for Snapdragon; verified on CPU fallback" |
| "AI Hub model" | "AI Hub–qualified custom-trained model" |
| "0.342 ms on Hexagon NPU" | "0.342 ms estimated (requires hardware verification)" |
| "Measured on Snapdragon X Elite" | "Projected for Snapdragon X Elite" |
| "QNN execution confirmed" | "QNN provider configured; execution requires Snapdragon hardware" |
