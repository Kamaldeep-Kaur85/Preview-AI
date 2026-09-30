# PreView AI — Model Evaluation Report

> **Honesty principle**: All metrics below were computed from actual code execution.
> Dataset and methodology are stated precisely. Status labels reflect verified results.

---

## 1. Executive Summary

| Metric | Result | Dataset | Status |
|:---|:---|:---|:---|
| **Validation Accuracy** | **100.0%** | Synthetic held-out (800 scenarios) | ✓ Verified |
| **Precision** | **100.0%** | Synthetic held-out | ✓ Verified |
| **Recall** | **100.0%** | Synthetic held-out | ✓ Verified |
| **F1 Score** | **1.000** | Synthetic held-out | ✓ Verified |
| **False Positives** | **0** | Synthetic held-out | ✓ Verified |
| **False Negatives** | **0** | Synthetic held-out | ✓ Verified |
| **Model Disk Footprint** | **12.3 KB** | — | ✓ Verified |
| **Inference Latency (CPU)** | **~0.10–0.14 ms** | Intel i7-10610U | ✓ Measured |
| **Peak Memory (CPU session)** | **~3.05 MB** | Intel i7-10610U | ✓ Measured |

> **⚠ Important**: These metrics are measured on a **synthetic held-out benchmark**, not on real-world projects.
> "100% validation accuracy" means 100% accuracy on the synthetic test split.
> Performance on unseen real-world project dependency patterns has not been separately benchmarked.

---

## 2. Dataset Description

| Property | Value |
|:---|:---|
| **Dataset type** | Synthetically generated software dependency scenarios |
| **Generator** | `generate_dependency_dataset()` in `app/ai/train_model.py` |
| **Total size** | 4,000 scenarios |
| **Train split** | 3,200 scenarios (80%) |
| **Validation split** | 800 scenarios (20%) |
| **Random seed** | Fixed: `seed=42` |
| **Real-world data** | None — all synthetic |
| **Scenario distribution** | Unrelated (40%), Direct dependency (25%), Indirect (15%), Test file (10%), Data/config (10%) |

### Synthetic Data Warning

The dataset is **entirely synthetically generated** using handcrafted rules for feature-label assignments. This means:

- Labels are deterministic functions of the feature values
- A sufficiently expressive model can learn these rules to near-perfection
- 100% validation accuracy on this benchmark does **not** imply 100% accuracy on real-world projects
- Real projects contain dynamic dependencies, implicit references, and patterns not captured in the synthetic distribution

---

## 3. Model Description

- **Model**: `preview_impact_predictor.onnx`
- **Architecture**: 2-layer MLP (16→48→32) with three output heads
- **Training**: Supervised multi-task backpropagation (Adam optimizer, 45 epochs, batch size 64)
- **Origin**: Custom-trained on synthetic data; **not** downloaded from Qualcomm AI Hub
- **Format**: ONNX Opset 17, IR version 9, FP32

---

## 4. Evaluation Methodology

### Binary Impact Classification

Impact probability threshold: `≥ 0.40` → classified as "affected".

Metrics computed on `y_impact_val` (ground truth) vs `pred_impact_binary`:
```
Accuracy  = (TP + TN) / N
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × (Precision × Recall) / (Precision + Recall)
```

### Risk Classification

Multi-class accuracy on `risk_logits` vs `y_risk_val`:
```
Risk Accuracy = correct risk class predictions / N
```

---

## 5. Test Execution Environment

- **Hardware**: On-device local host (Intel Core i7-10610U @ 1.80 GHz, AMD64)
- **OS**: Windows 11
- **Active Execution Provider**: ONNX Runtime `CPUExecutionProvider`
- **Snapdragon NPU**: Not present (x86/x64 development machine)
- **Network**: 100% offline

---

## 6. CPU Performance Metrics (Verified)

Run `python -m app.benchmark` to reproduce:

| Metric | Measured Value |
|:---|:---|
| Model load time | ~31–33 ms (CPU) |
| P50 inference latency | ~0.10–0.14 ms |
| P95 inference latency | ~0.20 ms |
| Throughput | ~32,000–34,000 inf/sec |
| Peak memory footprint | ~0.01–3.05 MB |

---

## 7. Snapdragon / NPU Performance Estimates

> **These numbers are NOT independently measured. They are estimates derived from operator analysis and offline AI Hub qualification.**

| Metric | Estimated Value | Basis |
|:---|:---|:---|
| P50 inference (NPU) | ~0.34 ms | AI Hub offline receipt (not live measurement) |
| Throughput (NPU) | ~12,840 inf/sec | AI Hub offline receipt |
| NPU memory | ~1.42 MB | AI Hub offline receipt |
| NPU speedup | ~4.7× over CPU | Derived from unverified estimates |

These estimates will be verified when the model is profiled on actual Snapdragon hardware via `qai-hub profile`.

---

## 8. How to Reproduce

### Re-run training + evaluation
```bash
python -m app.ai.train_model
```

### Run the evaluation pipeline
```bash
python -m app.evaluation
```

### Run the hardware benchmark
```bash
python -m app.benchmark
```

### Check AI Hub compliance
```bash
python -m app.ai.ai_hub_manager
```

---

## 9. Limitations

1. **Synthetic benchmark only**: Metrics are derived from synthetic data constructed to match known patterns. Real-world accuracy may differ.
2. **CPU-only verification**: All latency and memory measurements were taken on an Intel x86/x64 CPU. NPU execution has not been independently measured.
3. **Static analysis only**: The model predicts impact based on static AST/graph features. Dynamic runtime dependencies (subprocess calls, eval, dynamic imports) are not captured.
4. **Python-centric**: The dependency analyzer focuses on Python projects. Other languages have limited support.
5. **Small model**: 12.3 KB / ~2,400 parameters. Expressiveness is intentionally limited for speed and compactness.
