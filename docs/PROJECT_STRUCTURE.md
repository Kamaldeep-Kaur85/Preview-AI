# PreView AI — Project Structure

```
preview-ai/
│
├── README.md                        ← Project overview (start here)
├── requirements.txt                 ← Python dependencies
├── pyproject.toml                   ← Project metadata
├── run_preview_ai.bat               ← Development launcher (with console)
├── build_windows.bat                ← Production build (windowed EXE)
│
├── app/                             ← Main application source
│   ├── __init__.py
│   ├── main.py                      ← Entry point + PySide6 application
│   ├── benchmark.py                 ← Hardware inference benchmark tool
│   ├── evaluation.py                ← Model evaluation pipeline
│   │
│   ├── ai/                          ← AI inference and model management
│   │   ├── backend.py               ← Hardware detection + provider selection (CPU/QNN)
│   │   ├── impact_predictor.py      ← Orchestrates full inference pipeline
│   │   ├── context_builder.py       ← Graph → 16-feature vector
│   │   ├── model_manager.py         ← Model path resolution + auto-generation
│   │   ├── model_builder.py         ← ONNX model build entry point
│   │   ├── train_model.py           ← Neural network training + ONNX export
│   │   ├── ai_hub_manager.py        ← Qualcomm AI Hub compliance + compilation tools
│   │   ├── intent_parser.py         ← Natural language → structured action
│   │   ├── assistant_router.py      ← Routes AI queries to analysis functions
│   │   ├── explanation.py           ← Evidence-grounded explanation generator
│   │   ├── file_operations.py       ← File operation handlers
│   │   ├── global_search.py         ← Project-wide search
│   │   └── conversation_context.py  ← Conversation state management
│   │
│   ├── consequence/                 ← Impact classification and propagation
│   │   └── analyzer.py
│   │
│   ├── execution/                   ← Approval gate + file execution
│   │
│   ├── graph/                       ← Dependency graph models
│   │   ├── builder.py               ← StateGraph + GraphBuilder
│   │   └── models.py                ← Node, Edge, Evidence, ImpactResult
│   │
│   ├── parsing/                     ← Static analysis parsers
│   │   ├── python_parser.py         ← AST-based Python import/call detection
│   │   ├── config_parser.py         ← JSON/YAML/TOML reference parser
│   │   └── reference_detector.py   ← String path reference detector
│   │
│   ├── safety/                      ← Scope validation + safety guardrails
│   │
│   ├── simulation/                  ← Virtual state simulator
│   │   ├── simulator.py
│   │   └── virtual_state.py
│   │
│   ├── state/                       ← Filesystem scanner + watcher + index
│   │
│   ├── ui/                          ← PySide6 UI components
│   │
│   └── verification/                ← Post-action state comparison
│
├── models/
│   └── preview_impact_predictor.onnx    ← Trained impact predictor (12.3 KB)
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/                    ← Demo project files for testing
│   ├── unit/                        ← Per-component unit tests
│   ├── integration/                 ← End-to-end tests
│   └── safety/                      ← Safety invariant tests
│
├── examples/
│   └── demo_ml_project/             ← Interactive demo project
│       ├── app.py
│       ├── train.py
│       ├── evaluate.py
│       ├── dataset.csv
│       ├── config.json
│       └── requirements.txt
│
├── docs/                            ← Technical documentation
│   ├── ARCHITECTURE.md              ← System architecture + component inventory
│   ├── AI_PIPELINE.md               ← AI inference pipeline + model architecture
│   ├── SNAPDRAGON_AI.md             ← QNN/Snapdragon verified status audit
│   ├── MODEL_EVALUATION.md          ← Training, evaluation, benchmark results
│   ├── PERFORMANCE.md               ← CPU benchmarks + NPU estimates
│   ├── DEPENDENCY_ANALYSIS.md       ← Static analysis methodology
│   ├── FUTURE_STATE_SIMULATION.md   ← Virtual state simulation
│   ├── TESTING.md                   ← Test framework and how to run
│   ├── DEPLOYMENT.md                ← Windows deployment guide
│   ├── DEMO_GUIDE.md                ← Step-by-step demo walkthrough
│   ├── TROUBLESHOOTING.md           ← Common issues and fixes
│   ├── PROJECT_STRUCTURE.md         ← This file
│   ├── AI_HUB_INTEGRATION.md        ← AI Hub integration guide (historical)
│   ├── MODEL_OPTIMIZATION.md        ← Model optimization notes
│   ├── INSTALLATION.md              ← Installation guide
│   └── SYSTEM_REQUIREMENTS.md       ← Hardware/software requirements
│
├── build/                           ← Generated locally; not committed
├── dist/                            ← Generated locally; not committed
│   └── PreView-AI.exe
│
├── scratch/                         ← Development scratch scripts (not production)
│   ├── debug_gui.py
│   ├── test_step_by_step.py
│   └── test_load_project.py
│
└── .cache/                          ← Generated locally; not committed
```

---

## Key Entry Points

| Goal | Command |
|:---|:---|
| Run the app | `python -m app.main` or `run_preview_ai.bat` |
| Run with demo project | `run_preview_ai.bat --project "examples\demo_ml_project"` |
| Diagnostics | `python -m app.main --diagnostics` |
| Train / regenerate model | `python -m app.ai.train_model` |
| Run benchmark | `python -m app.benchmark` |
| Run evaluation | `python -m app.evaluation` |
| AI Hub compliance check | `python -m app.ai.ai_hub_manager` |
| Run tests | `pytest tests/` |
| Build executable | `build_windows.bat` |
