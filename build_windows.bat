@echo off
setlocal enabledelayedexpansion

title PreView AI — Windows Executable Build Script

rem Determine Project Root directory
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

cd /d "%PROJECT_ROOT%"

echo ============================================================
echo  Building PreView AI Executable...
echo  Project Root: %PROJECT_ROOT%
echo ============================================================

rem Locate working Python executable on D: drive or system
set "PYTHON_EXE="

if exist "D:\conda\python.exe" (
    "D:\conda\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=D:\conda\python.exe"
)

if not defined PYTHON_EXE if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    "%PROJECT_ROOT%\.venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
    for /f "tokens=*" %%I in ('where python 2^>nul') do (
        if not defined PYTHON_EXE (
            "%%I" -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PYTHON_EXE=%%I"
        )
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python installation not found or not functional.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%

rem Ensure PyInstaller is installed
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller into D:-based Python environment...
    "%PYTHON_EXE%" -m pip install pyinstaller --cache-dir "D:\PreViewAI\pip-cache"
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        echo.
        pause
        exit /b 1
    )
)

rem Define build, dist, and cache paths on D: drive to protect C: drive space
set "BUILD_DIR=%PROJECT_ROOT%\build"
set "DIST_DIR=%PROJECT_ROOT%\dist"

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

rem Clean previous build files if requested or stale
if exist "%BUILD_DIR%" (
    echo Cleaning previous build directory: %BUILD_DIR%
    rd /s /q "%BUILD_DIR%" >nul 2>&1
    mkdir "%BUILD_DIR%"
)

echo.
echo Launching PyInstaller production GUI build for "PreView-AI.exe"...
echo Mode: Windowed GUI (Subsystem: Windows, No Console)
echo Build Directory:  %BUILD_DIR%
echo Output Directory: %DIST_DIR%
echo.

"%PYTHON_EXE%" -m PyInstaller ^
    --name "PreView-AI" ^
    --onefile ^
    --windowed ^
    --clean ^
    --noconfirm ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    --paths "%PROJECT_ROOT%" ^
    --exclude-module "torch" ^
    --exclude-module "transformers" ^
    --add-data "%PROJECT_ROOT%\models\preview_impact_predictor.onnx;models" ^
    --add-data "%PROJECT_ROOT%\examples;examples" ^
    --hidden-import "PySide6" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "app" ^
    --hidden-import "app.ai.backend" ^
    --hidden-import "app.ai.model_manager" ^
    --hidden-import "app.ai.model_builder" ^
    --hidden-import "app.ai.impact_predictor" ^
    --hidden-import "app.ai.ai_hub_manager" ^
    --hidden-import "app.ai.train_model" ^
    --hidden-import "app.ai.intent_parser" ^
    --hidden-import "app.ai.explanation" ^
    --hidden-import "app.graph.builder" ^
    --hidden-import "app.graph.models" ^
    --hidden-import "app.simulation.simulator" ^
    --hidden-import "app.simulation.virtual_state" ^
    --hidden-import "app.simulation.diff" ^
    --hidden-import "app.consequence.analyzer" ^
    --hidden-import "app.safety.policy" ^
    --hidden-import "app.execution.executor" ^
    --hidden-import "app.verification.verifier" ^
    --hidden-import "app.state.watcher" ^
    --hidden-import "app.state.index_cache" ^
    --hidden-import "app.state.scanner" ^
    --hidden-import "app.parsing.python_parser" ^
    --hidden-import "app.parsing.config_parser" ^
    --hidden-import "app.parsing.reference_extractor" ^
    --hidden-import "app.parsing.import_resolver" ^
    --collect-submodules "app" ^
    "%PROJECT_ROOT%\app\main.py"

if errorlevel 1 (
    echo.
    echo [BUILD ERROR] PyInstaller build failed.
    echo.
    pause
    exit /b 1
)

rem Create backward-compatible alias "PreView AI.exe"
if exist "%DIST_DIR%\PreView-AI.exe" (
    copy /y "%DIST_DIR%\PreView-AI.exe" "%DIST_DIR%\PreView AI.exe" >nul 2>&1
)

echo.
echo ============================================================
if exist "%DIST_DIR%\PreView-AI.exe" (
    echo [BUILD SUCCESS] Production GUI Executable created successfully:
    echo  - Primary:   "%DIST_DIR%\PreView-AI.exe"
    echo  - Alias:     "%DIST_DIR%\PreView AI.exe"
    echo Subsystem:    Windows GUI (No Terminal / No CMD Window)
) else (
    echo [WARNING] Build completed but "%DIST_DIR%\PreView-AI.exe" was not found.
)
echo ============================================================
echo.

endlocal
