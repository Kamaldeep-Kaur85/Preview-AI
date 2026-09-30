# PreView AI — Snapdragon Execution Evidence

> **⚠ Important Notice**
>
> The Snapdragon X Elite hardware execution described in this document was **not independently verified** in the current development environment (Intel Core i7-10610U, AMD64).
>
> The log traces shown in Section 2 represent what **correct QNN execution would produce** on Snapdragon hardware when the QNN SDK (≥ v2.20) is installed and `QNNExecutionProvider` is available. They are not captured from a live hardware run in this environment.
>
> For verified current status of all claims, see [`SNAPDRAGON_AI.md`](SNAPDRAGON_AI.md).

---

## 1. Execution Architecture

PreView AI incorporates a dual-mode hardware detection pipeline:

**Snapdragon NPU Acceleration Path (Configured)**:
- Uses Qualcomm AI Engine Direct (QNN) SDK v2.20+ with `QnnHtp.dll`
- Targets sub-millisecond, ultra-low-power tensor inference on the Qualcomm Hexagon NPU
- Status: **IMPLEMENTED** — code is correctly written; requires Snapdragon hardware to activate

**CPU Fallback Path (Verified)**:
- Uses standard ONNX Runtime `CPUExecutionProvider`
- Operates on x86/x64 development machines without faking hardware presence
- Status: **VERIFIED** — confirmed operational on Intel Core i7-10610U

---

## 2. Expected QNN Initialization Trace (on Snapdragon Hardware)

When PreView AI runs on a correctly configured Snapdragon X Elite device with QNN SDK ≥ v2.20, the following initialization sequence is expected:

```text
[PreViewAI.backend] [INFO] Detecting hardware architecture... machine=ARM64, system=Windows
[PreViewAI.backend] [INFO] Processor: Snapdragon(R) X Elite - X1E80100 - Qualcomm(R) Oryon(TM) CPU @ 3.40 GHz
[PreViewAI.backend] [INFO] Qualcomm QNN SDK detected at C:\Qualcomm\QNN\lib\arm64x
[PreViewAI.backend] [INFO] Found QNN libraries: ['QnnHtp.dll', 'QnnSystem.dll', 'QnnHtpV73Stub.dll']
[PreViewAI.backend] [INFO] ONNX Runtime Available Providers: ['QNNExecutionProvider', 'CPUExecutionProvider']
[PreViewAI.backend] [INFO] Qualcomm QNNExecutionProvider detected! Activating QNNBackend (Hexagon NPU).
[PreViewAI.backend] [INFO] Configuring QNN provider options:
    backend_path = QnnHtp.dll
    htp_performance_mode = burst
    htp_graph_finalization_optimization_mode = 3
[PreViewAI.backend] [INFO] Loading model: preview_impact_predictor.onnx (12.3 KB)
[PreViewAI.backend] [INFO] Operator delegation: 8 of 8 nodes successfully delegated to Hexagon HTP (0 fallbacks)
    - Gemm nodes (5): Delegated to HTP Matrix Engine
    - Relu nodes (2): Delegated to HTP Vector Engine
    - Sigmoid nodes (1): Delegated to HTP Activation LUT
[PreViewAI.backend] [INFO] QNNBackend loaded preview_impact_predictor.onnx on Hexagon NPU in 14.20ms
```

> **Note**: This trace was NOT captured from a live hardware run in the current environment. It documents the expected output based on code analysis of `backend.py`.

---

## 3. Verified CPU Fallback Trace (Current Environment)

Actual trace on Intel Core i7-10610U, AMD64, Windows 11:

```text
[PreViewAI.backend] [INFO] Detecting hardware architecture... machine=AMD64, system=Windows
[PreViewAI.backend] [INFO] Processor: Intel(R) Core(TM) i7-10610U CPU @ 1.80GHz
[PreViewAI.backend] [INFO] Snapdragon signatures: not found in processor name
[PreViewAI.backend] [INFO] ONNX Runtime Available Providers: ['CPUExecutionProvider', 'AzureExecutionProvider']
[PreViewAI.backend] [INFO] QNNExecutionProvider not available. Using ONNX Runtime CPU fallback.
[PreViewAI.backend] [INFO] CPUBackend loaded preview_impact_predictor.onnx on CPU in 30.75ms
```

---

## 4. Hardware Comparison

| Parameter | Snapdragon Target | Dev Machine (Verified) |
|:---|:---|:---|
| Platform | Qualcomm Snapdragon X Elite (SC8380XP) | Intel(R) Core(TM) i7-10610U |
| Architecture | ARM64 (Qualcomm Oryon) | AMD64 (x86_64) |
| Active Provider | `QNNExecutionProvider` (configured) | `CPUExecutionProvider` (verified) |
| Backend | `QnnHtp.dll` | `onnxruntime.dll` |
| Snapdragon hardware | **REQUIRED — not present in dev env** | N/A |

---

## 5. Performance Comparison

| Metric | Snapdragon X Elite NPU (Estimated) | Intel i7 CPU (Verified) |
|:---|:---|:---|
| P50 Latency | 0.342 ms *(estimated)* | ~0.10–0.14 ms *(measured)* |
| P95 Latency | 0.418 ms *(estimated)* | ~0.20 ms *(measured)* |
| Throughput | 12,840 inf/sec *(estimated)* | ~32,000 inf/sec *(measured)* |
| Memory | 1.42 MB *(estimated)* | ~3.05 MB *(measured)* |
| Power | ~0.12 W *(estimated)* | ~1.85 W *(estimated)* |

> All NPU numbers are **estimates from the AI Hub offline qualification receipt**, not independently measured hardware results.

---

## 6. How to Reproduce

### CPU benchmark (any machine)
```bash
python -m app.benchmark
```

### CLI diagnostics
```bash
python -m app.main --diagnostics
```

### Snapdragon hardware benchmark (requires Snapdragon device)
On a Snapdragon X Elite / Plus device with QNN SDK installed:
```bash
python -m app.benchmark
```
The benchmark will automatically detect and use `QNNExecutionProvider` if available.
