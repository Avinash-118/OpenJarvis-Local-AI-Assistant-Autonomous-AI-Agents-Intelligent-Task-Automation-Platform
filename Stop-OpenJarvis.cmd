@echo off
setlocal
if exist "%~dp0jarvis_background.py" "%~dp0OpenJarvis\.venv\Scripts\python.exe" "%~dp0jarvis_background.py" --stop
"%~dp0OpenJarvis\.venv\Scripts\python.exe" "%~dp0OpenJarvis-Local.py" --stop
if errorlevel 1 pause
