# PreView AI — Benchmark Results

> Run `python -m app.benchmark` to reproduce CPU figures.
>
> For the full audit of Snapdragon/NPU numbers, see [SNAPDRAGON_AI.md](SNAPDRAGON_AI.md).

---

## 1. Local Host Benchmark (Verified)

**Hardware**: Intel(R) Core(TM) i7-10610U CPU @ 1.80GHz  
**Architecture**: AMD64  
**OS**: Windows 11  
**Backend**: ONNX Runtime `CPUExecutionProvider`  
**Model**: `preview_impact_predictor.onnx` (12.0–12.3 KB)  
**Iterations**: 100 timed runs, 10 warmup  

| Metric | Measured Value |
|:---|:---|
| **Execution Provider** | `CPUExecutionProvider` |
| **Model Load Time** | ~30–33 ms |
| **P50 (Median) Latency** | ~0.10–0.14 ms |
| **P95 Latency** | ~0.20 ms |
| **Min Latency** | ~0.10 ms |
| **Average Latency** | ~0.14 ms |
| **Throughput** | ~32,000–34,000 inf/sec |
| **Peak Memory** | ~0.01–3.05 MB |

---

## 2. Snapdragon X Elite Benchmark (Estimated — Not Independently Measured)

> **⚠ The following values are NOT measured results.**
> These are estimates from the AI Hub offline qualification receipt in `ai_hub_manager.profile_on_snapdragon_device()`.
> They are **not** captured from a live hardware run.
> **Snapdragon hardware execution could not be independently verified in the current environment.**

**Target Hardware**: Qualcomm Snapdragon X Elite (SC8380XP)  
**Target Backend**: `QNNExecutionProvider` (`QnnHtp.dll`)  

| Metric | Estimated Value | Source |
|:---|:---|:---|
| **Execution Provider** | `QNNExecutionProvider` | Configured in code |
| **Accelerator** | Qualcomm Hexagon HTP | Configured in code |
| **Model Load Time** | 14.20 ms | AI Hub offline receipt |
| **P50 Latency** | 0.342 ms | AI Hub offline receipt |
| **P95 Latency** | 0.418 ms | AI Hub offline receipt |
| **Throughput** | 12,840 inf/sec | AI Hub offline receipt |
| **Peak Memory** | 1.42 MB | AI Hub offline receipt |
| **Power** | ~0.12 W | AI Hub offline receipt |

---

## 3. Validation Status

| Layer | Status |
|:---|:---|
| CPU inference | **VALIDATED — Benchmarked on Intel i7** |
| QNN provider code | **IMPLEMENTED — Not yet activated on hardware** |
| Snapdragon NPU execution | **REQUIRES HARDWARE VERIFICATION** |

---

## 4. Reproducing the Benchmark

```bash
# CPU benchmark (works on any machine with Python + onnxruntime)
python -m app.benchmark

# Check active hardware + provider
python -m app.main --diagnostics

# Full evaluation including model metrics
python -m app.evaluation
```
