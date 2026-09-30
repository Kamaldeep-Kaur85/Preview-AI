# PreView AI — Installation Guide

## End-User Installation (Standalone Binary)

No Python, compiler, or development tools are needed.

### Step 1: Download
Obtain the standalone executable package:
- File: `PreView-AI.exe` (or archive `PreView-AI-Windows.zip`)

### Step 2: Placement
Copy or move `PreView-AI.exe` to your preferred folder:
```
C:\Program Files\PreView AI\PreView-AI.exe
-- OR --
C:\Users\<username>\AppData\Local\Programs\PreView AI\PreView-AI.exe
-- OR --
Any desktop or local folder
```

### Step 3: Launch
Double-click `PreView-AI.exe`:
- **No Command Prompt window** or terminal opens.
- The PreView AI GUI window opens immediately.
- If Windows Defender SmartScreen shows an unrecognized app prompt on first run, select **More info** → **Run anyway**.

---

## Developer Installation (From Source)

For developers contributing to or modifying PreView AI:

### Prerequisites
- Windows 10 / Windows 11 (64-bit x64 or ARM64)
- Python 3.10+ (Python 3.11, 3.12, or 3.13 recommended)
- Git for Windows

### Step 1: Clone Repository
```powershell
git clone https://github.com/example/preview-ai.git
cd preview-ai
```

### Step 2: Set Up Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Run Development Launcher
```cmd
run_preview_ai.bat
```
*(The developer batch file launches with live console output for debugging.)*

### Step 5: Build Production Executable
```cmd
build_windows.bat
```
The output executable will be placed in `dist\PreView-AI.exe`.
