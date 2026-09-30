# PreView AI — Troubleshooting Guide

This guide provides actionable solutions for common deployment, startup, and runtime issues.

---

## 1. Windows SmartScreen: "Windows protected your PC"

### Symptom
When double-clicking `PreView-AI.exe`, Windows displays a blue SmartScreen alert:
> *"Windows Defender SmartScreen prevented an unrecognized app from starting."*

### Cause
`PreView-AI.exe` is a custom-compiled Windows executable that has not been digitally signed with an expensive Extended Validation (EV) code-signing certificate. Windows displays this warning by default for new or unrecognized binaries.

### Resolution
1. Click **More info** on the SmartScreen dialog.
2. Click **Run anyway**.
3. The application will launch normally and will not prompt again on subsequent executions.
*(Note: Never disable Windows Defender or system antivirus protections.)*

---

## 2. Application Closes Immediately or Does Not Launch

### Symptom
Double-clicking `PreView-AI.exe` shows a loading spinner briefly, but no window appears.

### How to Diagnose
Check the diagnostic log file:
```cmd
notepad "%LOCALAPPDATA%\PreView AI\logs\preview_ai.log"
```
*(Path: `C:\Users\<username>\AppData\Local\PreView AI\logs\preview_ai.log`)*

### Common Causes & Fixes
- **Missing Visual C++ Redistributable**:
  - Install the official Microsoft Visual C++ 2015–2022 Redistributable (x64) from Microsoft's official download portal.
- **Temporary Extraction Directory Locked**:
  - PyInstaller extracts runtime files to `%TEMP%\_MEIxxxxxx`. If your disk is full or `%TEMP%` has restricted permissions, clear temporary files (`Win+R` → `%TEMP%`) and ensure at least 500 MB of free disk space.
- **Corrupted Model File**:
  - Verify that `models/preview_impact_predictor.onnx` is intact (12.3 KB). If running from source, delete the file and run `python app/ai/train_model.py` to regenerate it.

---

## 3. QNN / Snapdragon Acceleration Unavailable

### Symptom
Diagnostic output or logs report:
```
[INFO] Device: ... Using ONNX Runtime CPU fallback.
```

### Explanation
PreView AI features an adaptive hardware detection pipeline:
- On **Snapdragon X Elite / Copilot+ PCs** (ARM64 Windows), PreView AI automatically binds to Qualcomm QNN HTP (Hexagon NPU).
- On **Intel or AMD x86-64 PCs**, the Qualcomm NPU is physically absent. PreView AI automatically falls back to ONNX Runtime's high-speed CPU Execution Provider.
- Both execution paths are functionally identical; the CPU fallback executes the impact predictor network in ~1.61 ms, ensuring responsive operations on all machines.

---

## 4. File Permission or Access Errors During Execution

### Symptom
PreView AI reports:
> *"Access Denied: Could not modify / rename target file."*

### Cause
The target file or folder is:
1. Marked as read-only.
2. Open and locked by another application (e.g., Visual Studio, Excel, or Python).
3. Located in a protected Windows directory (e.g., `C:\Windows` or `C:\Program Files`).

### Resolution
- Close applications currently holding a lock on the target file.
- If working with system directories, ensure you have appropriate administrator permissions.
- PreView AI's safety guardrails automatically block dangerous modifications to Windows system roots and active git metadata folders (`.git/`).

---

## 5. Locating Application Logs

PreView AI records all deployment, startup, inference, and error events to:
```
%LOCALAPPDATA%\PreView AI\logs\preview_ai.log
```
To view the log in PowerShell:
```powershell
Get-Content "$env:LOCALAPPDATA\PreView AI\logs\preview_ai.log" -Tail 50
```
To view the log in Command Prompt:
```cmd
type "%LOCALAPPDATA%\PreView AI\logs\preview_ai.log"
```
