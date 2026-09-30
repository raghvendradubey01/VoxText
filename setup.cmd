@echo off
REM ---------------------------------------------------------------
REM Create/reuse the project virtual environment with a *working*
REM interpreter.  C:\Users\HP\anaconda3 is a broken leftover install
REM that sits first on PATH, so it must never be used.
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "WORKING_PY=C:\Users\HP\AppData\Local\Programs\Python\Python314\python.exe"

if not exist "%WORKING_PY%" (
    echo [setup] ERROR: %WORKING_PY% not found.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment with %WORKING_PY%
    "%WORKING_PY%" -m venv .venv
    if errorlevel 1 (
        echo [setup] ERROR: venv creation failed.
        exit /b 1
    )
)

set "VPY=%~dp0.venv\Scripts\python.exe"

echo [setup] Interpreter: 
"%VPY%" -c "import sys;print(sys.version)"
if errorlevel 1 exit /b 1

echo [setup] Upgrading pip...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 exit /b 1

echo [setup] Installing requirements...
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo [setup] ERROR: dependency installation failed.
    exit /b 1
)

echo [setup] DONE
