# PreView AI — Testing

## 1. Test Framework

**Framework**: pytest  
**Location**: `tests/`  
**Structure**:

```
tests/
├── conftest.py           ← shared fixtures
├── fixtures/             ← test project file trees
├── unit/                 ← unit tests per module
├── integration/          ← end-to-end integration tests
└── safety/               ← safety and scope-boundary tests
```

---

## 2. Running Tests

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/unit/test_graph.py

# Run safety tests only
pytest tests/safety/ -v
```

---

## 3. Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation:
- Graph builder — node + edge creation, traversal
- Parsers — Python AST import detection, config reference parsing
- State index — scan, update, path normalization
- Context builder — feature vector extraction
- Consequence analyzer — impact propagation
- Simulation engine — virtual state operations

### Integration Tests (`tests/integration/`)

Test end-to-end scenarios against fixture projects:
- Project load → graph build → impact query
- File change detection → state update → impact propagation
- AI-proposed action → simulation → consequence report

### Safety Tests (`tests/safety/`)

Validate critical safety invariants:
- Scope containment: operations outside monitored root are blocked
- Simulation isolation: real filesystem unchanged during simulation
- Stale preview invalidation: execution blocked when state has changed
- Approval gate: no action executes without user approval

---

## 4. Test Fixtures

Demo ML project fixture (`tests/fixtures/demo_ml_project/`):

```
demo_ml_project/
├── app.py          ← imports train.py, loads model.pkl
├── train.py        ← reads dataset.csv, writes model.pkl
├── evaluate.py     ← reads dataset.csv, loads model.pkl
├── dataset.csv     ← referenced by train.py, evaluate.py
├── config.json     ← referenced by app.py
└── requirements.txt
```

Known relationships are pre-established in this fixture and used as ground truth for impact detection tests.

---

## 5. Model Training Test

The model training pipeline is testable independently:

```bash
python -m app.ai.train_model
```

Expected output:
```
Epoch 45/45 | Loss: 0.0xxx | Val Acc: 100.0% | F1: 1.000 | Risk Acc: 100.0%
Final Validation Accuracy: 100.00%
Final F1 Score: 1.0000
```

> **Note**: 100% validation accuracy is expected because the dataset is synthetically generated with deterministic labels. See [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md) for full caveats.

---

## 6. AI Hub Compliance Test

```bash
python -m app.ai.ai_hub_manager
```

This runs `verify_model_compliance()` locally (no network required) and confirms:
- ONNX Opset 17 ✓
- All 8 operators in Hexagon HTP set ✓
- 0 unsupported operators ✓

---

## 7. Hardware Benchmark

```bash
python -m app.benchmark
```

Runs 10 warmup + 100 timed inference iterations on the current hardware.  
Outputs min, average, P50, P95, throughput, and execution provider.

---

## 8. Diagnostics

```bash
python -m app.main --diagnostics
```

Reports:
- Detected CPU/architecture
- Whether Snapdragon hardware is detected
- Active ONNX Runtime execution provider
- Model name and load time
- Last inference time

---

## 9. Known Limitations of Current Test Suite

- **No Snapdragon hardware tests**: QNN provider path is not covered by automated tests; requires physical Snapdragon device
- **Synthetic benchmark only**: Model evaluation tests use synthetically generated data, not real-world project dependency data
- **UI not under automated test**: PySide6 UI interaction is not covered by pytest; manual testing required
