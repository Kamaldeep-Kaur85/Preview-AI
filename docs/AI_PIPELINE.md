# PreView AI — AI Pipeline

## 1. On-Device Inference Pipeline

```
File Explorer
       ↓
Incremental Scanner (mtime + size filter)
       ↓
Change Detection (Filesystem Watcher / User Selection)
       ↓
Project Dependency Graph (AST, imports, calls, symbols)
       ↓
Context Builder (16-feature normalized candidate vectors)
       ↓
On-Device AI Model (preview_impact_predictor.onnx)
       ↓
ONNX Runtime Engine (Opset 17, IR v9)
       ↓
┌──────────────────────────┴────────────────────────────┐
│                                                       │
▼                                                       ▼
[Snapdragon Hardware — if detected]          [Non-Snapdragon / Dev Fallback]
QNN Execution Provider (QnnHtp.dll)          CPU Execution Provider
Hexagon NPU / HTP (CONFIGURED)               Multi-threaded CPU (VERIFIED)
       │                                                │
└──────────────────────────┬────────────────────────────┘
                           ↓
                Impact Prediction & Ranking
                           ↓
                   Existing AI / Copilot Panel
                           ↓
                Future-State Consequence Preview
```

---

## 2. Model Architecture

**Model**: `preview_impact_predictor.onnx`

**Architecture**: Multi-Head Deep Representation Network (MLP)

| Layer | Shape | Activation |
|:---|:---|:---|
| Input `features` | `[batch_size, 16]` float32 | — |
| Hidden 1 (Gemm) | `[batch_size, 48]` | ReLU |
| Hidden 2 (Gemm) | `[batch_size, 32]` | ReLU |
| Head 1 `impact_scores` | `[batch_size, 1]` | Sigmoid |
| Head 2 `risk_logits` | `[batch_size, 4]` | (Softmax at inference) |
| Head 3 `consequence_logits` | `[batch_size, 5]` | (Softmax at inference) |

**ONNX Nodes**: 8 total — Gemm×5, Relu×2, Sigmoid×1

---

## 3. Input Feature Vector (16 features)

| Index | Feature | Description |
|:---|:---|:---|
| 0 | `is_direct_edge` | Direct graph edge to target (0/1) |
| 1 | `path_distance_score` | Normalized graph hop distance (0–1) |
| 2 | `symbol_reference_count` | Normalized symbol usage count (0–1) |
| 3 | `is_test_file` | Is this a test file? (0/1) |
| 4 | `is_import` | Import edge type (0/1) |
| 5 | `is_load` | File load edge type (0/1) |
| 6 | `is_read` | File read edge type (0/1) |
| 7 | `is_ref` | Reference edge type (0/1) |
| 8 | `complexity_score` | File complexity heuristic (0–1) |
| 9 | `op_delete` | Operation is DELETE (0/1) |
| 10 | `op_modify` | Operation is MODIFY (0/1) |
| 11 | `op_move` | Operation is MOVE (0/1) |
| 12 | `op_rename` | Operation is RENAME (0/1) |
| 13 | `is_critical_path` | Critical path indicator (0/1) |
| 14 | `file_depth_score` | Directory depth score (0–1) |
| 15 | `stem_name_overlap` | Filename stem similarity (0/1) |

---

## 4. Output Heads

### Head 1 — `impact_scores` `[batch_size, 1]`
Continuous impact probability (0.0 = unaffected → 1.0 = highly affected).  
Threshold: ≥ 0.35 for inclusion in impact list.

### Head 2 — `risk_logits` `[batch_size, 4]`
Risk classification logits. Classes: `LOW=0, MEDIUM=1, HIGH=2, BLOCKED=3`.

### Head 3 — `consequence_logits` `[batch_size, 5]`
Consequence category logits. Classes: `Direct=0, Indirect=1, Test=2, Data Load=3, Collateral=4`.

---

## 5. Model Training

**Source**: `app/ai/train_model.py` + `app/ai/model_builder.py`

- **Dataset**: Synthetically generated dependency scenarios (`generate_dependency_dataset()`)
- **Size**: 4,000 scenarios, 80/20 train/validation split
- **Seed**: Fixed at 42 for reproducibility
- **Optimizer**: Adam (lr=0.005, weight_decay=1e-4)
- **Epochs**: 45
- **Loss**: Multi-task — Binary Cross-Entropy (impact) + Cross-Entropy (risk + consequence)
- **Export**: ONNX Opset 17, IR version 9 via `onnx.helper`

To retrain and regenerate the model:
```bash
python -m app.ai.train_model
```

---

## 6. Context Builder

`app/ai/context_builder.py` extracts the 16-feature vector from the live dependency graph:

1. Finds all graph nodes reachable from the target
2. For each candidate node, computes edge distances, reference counts, edge types
3. Normalizes features to [0, 1]
4. Returns a `[N, 16]` float32 numpy array for batch inference

---

## 7. Backend Selection

`app/ai/backend.py` → `create_best_backend()`:

```python
if "QNNExecutionProvider" in ort.get_available_providers():
    return QNNBackend()   # Snapdragon Hexagon NPU
else:
    return CPUBackend()   # CPU fallback
```

**QNNBackend** (`IMPLEMENTED`): Configures `QNNExecutionProvider` with `QnnHtp.dll`, burst mode, and HTP graph optimization level 3.

**CPUBackend** (`VERIFIED`): Standard `CPUExecutionProvider`. Confirmed operational on x86/x64 dev machines.

---

## 8. AI Hub Integration

See [`SNAPDRAGON_AI.md`](SNAPDRAGON_AI.md) for the full verified status of Qualcomm AI Hub integration.

The `app/ai/ai_hub_manager.py` module provides:
- `verify_model_compliance()` — checks ONNX opset + HTP operator coverage (implemented, verified by code)
- `compile_model()` — submits compilation job to AI Hub if SDK + token present; otherwise returns offline qualification receipt
- `profile_on_snapdragon_device()` — submits profiling job if SDK + token present; otherwise returns estimated numbers

> **Important**: When no live AI Hub token is present, the returned profile metrics are **estimated values**, not measured hardware results.
