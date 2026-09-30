@echo off
REM ---------------------------------------------------------------
REM Start VoxText locally.
REM
REM Always launches through .venv\Scripts\python.exe rather than a bare
REM "python" from PATH: PATH currently resolves "python" to the broken,
REM half-deleted C:\Users\HP\anaconda3 install, which dies with
REM "ModuleNotFoundError: No module named 'encodings'" before any of
REM this code runs.
REM
REM Usage:
REM   run.cmd              -> serve on http://127.0.0.1:8000
REM   run.cmd --reload     -> also restart on code changes
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run] No virtual environment yet - running setup first.
    call setup.cmd
    if errorlevel 1 (
        echo [run] ERROR: setup failed, see setup.log
        exit /b 1
    )
)

echo.
echo   VoxText is starting...
echo   Open:  http://127.0.0.1:8000
echo   Docs:  http://127.0.0.1:8000/api/docs
echo   Stop:  Ctrl+C
echo.

".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 %*
