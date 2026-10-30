@echo off
setlocal
"%~dp0OpenJarvis\.venv\Scripts\python.exe" "%~dp0OpenJarvis-Local.py"
if errorlevel 1 (
    pause
    exit /b 1
)
if exist "%~dp0.openjarvis-runtime\background-voice-enabled.json" start "" /b "%~dp0OpenJarvis\.venv\Scripts\pythonw.exe" "%~dp0jarvis_background.py"
