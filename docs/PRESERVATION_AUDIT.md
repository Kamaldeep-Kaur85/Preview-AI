# PreView AI — Preservation Audit

> **Purpose**: Document every existing feature, its UI location, current implementation,
> what will be changed internally, and what must remain identical.
>
> This audit was completed BEFORE any code modifications.

---

## 1. Feature Inventory

### 1.1 File Explorer (LEFT PANEL)

| Feature | UI Location | Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|:---|
| File Tree (QTreeView) | Left sidebar | `_left_tree` in `main.py` | None | ✓ |
| Folder navigation | Tree item click | QFileSystemModel signals | None | ✓ |
| Context menu (right-click) | Tree/file list | `_show_context_menu()` | None | ✓ |
| File selection | Single click on file | `_on_tree_clicked()` | None | ✓ |

### 1.2 Center Panel

| Feature | UI Location | Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|:---|
| File list / detail view | Center area | `_file_table` | None | ✓ |
| Graph visualization tab | Center tab | Graph widget | None | ✓ |
| Simulation view | Center panel | Simulation display | None | ✓ |

### 1.3 Right Panel — AI Copilot

| Feature | UI Location | Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|:---|
| AI chat panel | Right side | `_ai_page_widget` | Backend only | ✓ |
| AI questions/answers | Chat area | `assistant_router.py` | Backend only | ✓ |
| AI status badge | Panel header | `_ai_status_badge` | Text updated from detection | ✓ |
| Diagnostics dialog | Menu/badge click | `_show_ai_diagnostics()` | Honest metrics | ✓ |

### 1.4 Toolbar

| Feature | UI Location | Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|:---|
| Back/Forward/Up | Toolbar left | Navigation buttons | None | ✓ |
| Path bar | Toolbar center | Address bar | None | ✓ |
| Search (🔍) | Toolbar right | Global search | None | ✓ |
| AI toggle (✨) | Toolbar right | AI panel toggle | None | ✓ |
| Index as Project (⚡) | Toolbar | Project indexing | None | ✓ |

### 1.5 AI / Intelligence Engine

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| ModelManager | `app/ai/model_manager.py` | Fix AI Hub claims, add honest evaluation | Public API preserved ✓ |
| Impact Predictor | `app/ai/impact_predictor.py` | Improve accuracy, honest reporting | Interface preserved ✓ |
| Intent Parser | `app/ai/intent_parser.py` | None | ✓ |
| Context Builder | `app/ai/context_builder.py` | None | ✓ |
| Assistant Router | `app/ai/assistant_router.py` | None | ✓ |
| Explanation Engine | `app/ai/explanation.py` | None | ✓ |
| Backend Detection | `app/ai/backend.py` | Strengthen QNN/device detection | ✓ |
| Model Builder | `app/ai/model_builder.py` | Fix misleading AI Hub claims in metadata | Architecture preserved ✓ |

### 1.6 Dependency Graph

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| StateGraph | `app/graph/builder.py` | None | ✓ |
| GraphBuilder | `app/graph/builder.py` | None | ✓ |
| Python parser (AST) | `app/parsing/python_parser.py` | None | ✓ |
| Config parser | `app/parsing/config_parser.py` | None | ✓ |
| Reference detector | `app/parsing/reference_detector.py` | None | ✓ |

### 1.7 Consequence Engine

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| ConsequenceAnalyzer | `app/consequence/analyzer.py` | None | ✓ |
| Simulator | `app/simulation/simulator.py` | None | ✓ |
| Virtual State | `app/simulation/virtual_state.py` | None | ✓ |

### 1.8 Safety & Execution

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| SafetyPolicy | `app/safety/policy.py` | None | ✓ |
| Executor | `app/execution/executor.py` | None | ✓ |
| Verifier | `app/verification/verifier.py` | None | ✓ |

### 1.9 File Operations

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| Create | `FileOperationsEngine` | None | ✓ |
| Delete | `FileOperationsEngine` | None | ✓ |
| Rename | `FileOperationsEngine` | None | ✓ |
| Move | `FileOperationsEngine` | None | ✓ |
| Copy | `FileOperationsEngine` | None | ✓ |
| Edit/Modify | `FileOperationsEngine` | None | ✓ |

### 1.10 Other Features

| Feature | Current Implementation | Internal Change | Must Remain Identical |
|:---|:---|:---|:---|
| Global search | `app/ai/global_search.py` | None | ✓ |
| Conversation context | `app/ai/conversation_context.py` | None | ✓ |
| Index cache | `app/state/index_cache.py` | None | ✓ |
| File watcher | `app/state/watcher.py` | None | ✓ |
| Project detector | `app/state/project_detector.py` | None | ✓ |
| Scanner | `app/state/scanner.py` | None | ✓ |
| Demo project | `examples/demo_ml_project/` | None | ✓ |
| Operation history | Event history in service | None | ✓ |
| CPU fallback | `CPUBackend` | None | ✓ |
| ONNX inference | ONNX Runtime session | None | ✓ |
| QNN detection | `backend.py` detection | Strengthen | ✓ |
| Keyboard behavior | Enter/Shift+Enter | None | ✓ |
| Startup behavior | `main.py` entry | None | ✓ |

---

## 2. User Workflow (MUST NOT CHANGE)

```
Search → Understand → Predict → Simulate → Approve → Act → Verify
```

---

## 3. Issues Found During Audit

### 3.1 CRITICAL: Dishonest Evaluation Reporting
- `docs/MODEL_EVALUATION.md` claims "✓ Exceeds Target" when actual metrics **FAIL** targets:
  - Accuracy: **75.0%** vs target **>95%** → claims "Exceeds Target" ❌
  - Precision: **66.7%** vs target **>90%** → claims "Exceeds Target" ❌
  - Recall: **83.3%** vs target **>95%** → claims "Exceeds Target" ❌
  - F1: **0.741** vs target **>0.90** → claims "Exceeds Target" ❌
  - False Positives: **5** vs target **0** → claims "Zero Spurious Alarms" ❌
  - False Negatives: **2** vs target **0** → claims "Zero Missed Dependencies" ❌
- The `evaluation.py` template ALWAYS outputs "Exceeds Target" regardless of actual values

### 3.2 CRITICAL: False "AI Hub" Claims
- `model_builder.py` creates a **randomly initialized, hand-tuned ONNX model**
- It is NOT sourced from Qualcomm AI Hub
- Metadata claims: "Qualcomm AI Hub-optimized ONNX model" — **false**
- README refers to "Qualcomm AI Hub" integration — **misleading**
- The model was never trained, compiled, or downloaded from aihub.qualcomm.com

### 3.3 Evaluation Template Always Claims 100% Match
- `evaluation.py` template hardcodes "Verified 100% match" for ALL cases
- Even when actual predictions don't match

### 3.4 Model Delete case returns UNKNOWN risk
- "Delete model.pkl" returns risk `UNKNOWN` instead of expected `HIGH`

### 3.5 Benchmark lacks min/max/memory/precision reporting
- `app/benchmark.py` missing: min, max, memory, precision fields

---

## 4. Changes To Be Made

### Backend-Only Changes (NO UI changes):

1. **Fix evaluation report generator** — compute honest status labels based on actual results
2. **Fix model metadata** — remove false "AI Hub-optimized" claims, describe accurately
3. **Improve model weights** — tune the hand-crafted ONNX model to reduce FP/FN
4. **Add benchmark completeness** — min, max, memory, model precision
5. **Add honest documentation** — AI_HUB_INTEGRATION.md, SNAPDRAGON_BENCHMARK.md
6. **Remove false claims from README** — replace with accurate statements
7. **Clean __pycache__ from tracking**
8. **Add new tests** — for benchmarking, evaluation, honest reporting

### What Will NOT Change:

- UI layout, colors, typography, icons
- Navigation, toolbar, panels, tabs
- File explorer appearance
- AI panel appearance
- Graph appearance
- Approval workflow
- Demo project
- User workflow
- Keyboard shortcuts
- Context menu
- Startup behavior
- Public API signatures
