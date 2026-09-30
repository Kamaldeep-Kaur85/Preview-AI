@echo off
setlocal enabledelayedexpansion

title PreView AI — See Consequences Before Your Computer Acts

rem Determine Project Root directory from batch file path
set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

cd /d "%PROJECT_ROOT%"

echo ============================================================
echo  Launching PreView AI...
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
    echo [ERROR] Could not locate a working Python installation.
    echo Please ensure Python is installed and accessible.
    echo.
    pause
    exit /b 1
)

rem Verify main entry point exists
if not exist "%PROJECT_ROOT%\app\main.py" (
    echo [ERROR] Application entry point "%PROJECT_ROOT%\app\main.py" was not found!
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
echo Starting PreView AI...
echo.

"%PYTHON_EXE%" "%PROJECT_ROOT%\app\main.py" %*

if errorlevel 1 (
    echo.
    echo [NOTICE] PreView AI exited with error code %ERRORLEVEL%.
    pause
)

endlocal
