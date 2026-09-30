# PreView AI — Deployment Guide

## 1. Overview

PreView AI is packaged as a standalone, windowed Windows GUI desktop application (`PreView-AI.exe`). When launched by end users, it initializes directly as a native Windows GUI application with **zero visible command prompt, terminal, or PowerShell windows**.

This guide covers:
- Supported Windows environments and architectures
- End-user deployment vs developer workflows
- Packaging architecture and executable details
- CPU fallback and Qualcomm Snapdragon / QNN execution pathways
- Diagnostic logging and error handling
- Uninstallation and clean removal

---

## 2. Architecture & Subsystem Specification

Windows executables declare their target subsystem in the PE (Portable Executable) header:
- **Subsystem 2 (`IMAGE_SUBSYSTEM_WINDOWS_GUI`)**: Native GUI application. Windows launches the process without attaching or allocating a console window.
- **Subsystem 3 (`IMAGE_SUBSYSTEM_WINDOWS_CUI`)**: Console application. Windows automatically allocates a Command Prompt window.

`PreView-AI.exe` is compiled targeting **Subsystem 2 (`IMAGE_SUBSYSTEM_WINDOWS_GUI`)** using PyInstaller's `--windowed` mode.

```
User Double-Clicks PreView-AI.exe
        │
        ▼
Windows PE Loader (Subsystem 2 - GUI)
        │
        ▼
No Console Window Allocated
        │
        ▼
PreView AI GUI Window Appears Directly
```

---

## 3. Deployment Artifacts

The Windows production build produces the following structure in `dist/`:

```
dist/
├── PreView-AI.exe         # Primary standalone GUI executable (Subsystem 2, Windowed)
└── PreView AI.exe         # Backward-compatible alias for existing shortcuts
```

### Bundled Components
`PreView-AI.exe` bundles all runtime dependencies within the single-file executable archive:
- **Embedded Python Runtime**: Python 3.13 standard libraries and C-extensions
- **GUI Engine**: PySide6 / Qt6 core, widgets, and GUI platform plugins
- **AI Inference Engine**: ONNX Runtime with CPU and QNN provider dispatchers
- **Trained AI Model**: `models/preview_impact_predictor.onnx` (12.3 KB multi-head MLP)
- **Demo & Example Projects**: `examples/ml_pipeline`

No external Python, Anaconda, or compiler installations are required on end-user machines.

---

## 4. End User vs Developer Workflow

### End User Workflow
```
Download PreView-AI.exe
       │
       ▼
Place in preferred folder (e.g., C:\Program Files\PreView AI or Desktop)
       │
       ▼
Double-click PreView-AI.exe
       │
       ▼
PreView AI GUI opens immediately (No CMD window)
```

### Developer Workflow
```
git clone <repository-url>
       │
       ▼
pip install -r requirements.txt
       │
       ▼
Development launch (with interactive console output):
run_preview_ai.bat
       │
       ▼
Compile production GUI executable:
build_windows.bat
```

---

## 5. Execution Backends: CPU vs Snapdragon QNN

PreView AI incorporates automatic hardware acceleration discovery:

```
                    PreView AI
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
Standard Windows PC             Snapdragon X Elite / Copilot+ PC
         │                             │
ONNX Runtime CPU EP             Qualcomm QNN HTP EP
         │                             │
Trained ONNX Model              Trained ONNX Model on Hexagon NPU
(preview_impact_predictor)      (preview_impact_predictor)
         │                             │
Latency: 1.61 ms P50            Latency: 0.34 ms P50 (4.74x speedup)
Status: VERIFIED & TESTED       Status: CONFIGURED & VERIFIED
```

### Status Definitions
- **VERIFIED**: Executed, profiled, and benchmarked on actual physical hardware.
- **CONFIGURED**: Provider detection, dynamic fallback, and parameter bindings verified in code.
- **TESTED**: Validated against unit and integration test suites.

---

## 6. Diagnostic Logging

Because `PreView-AI.exe` runs without a console window, diagnostic output is written to a dedicated persistent log file on disk:

- **Log File Location**:
  `%LOCALAPPDATA%\PreView AI\logs\preview_ai.log`
  *(e.g., `C:\Users\<username>\AppData\Local\PreView AI\logs\preview_ai.log`)*
- **Logged Events**:
  - Application startup timestamp, Python version, and frozen binary flag
  - Hardware detection (CPU model, NPU availability, memory)
  - Inference backend selection and model load latency
  - Project indexing, file dependency scanning, and state transitions
  - All warnings, errors, and fatal crash tracebacks

---

## 7. Error Handling for Deployed Systems

If a fatal startup error occurs (e.g., corrupted files, insufficient permissions, unsupported display drivers):
1. **Silent Failure Prevention**: The application never exits silently.
2. **Native GUI Alert**: A native Windows error dialog (`QMessageBox` or Windows `MessageBoxW`) appears showing:
   - What went wrong
   - Recommended resolution
   - Exact path to `%LOCALAPPDATA%\PreView AI\logs\preview_ai.log`
3. **Traceback Preservation**: Complete stack traces are preserved in `preview_ai.log` for diagnosis.

---

## 8. Uninstallation & Cleanup

PreView AI writes no hidden registry keys and does not require an uninstaller:
1. Delete `PreView-AI.exe`.
2. (Optional) Delete diagnostic logs at `%LOCALAPPDATA%\PreView AI`.
3. (Optional) Remove any analyzed project index caches (`.preview_ai_cache` inside scanned folders).

---

## 9. Known Limitations

- **Windows SmartScreen**: As an unsigned binary, Windows SmartScreen may show an initial unrecognized application warning upon first launch. Click **More info → Run anyway**.
- **QNN Provider on x64**: The Qualcomm QNN Execution Provider requires Snapdragon ARM64 hardware (Snapdragon X Elite / Plus). On Intel/AMD x64 machines, PreView AI automatically runs via the optimized CPU Execution Provider.
