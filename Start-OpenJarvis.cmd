@echo off
setlocal
"%~dp0OpenJarvis\.venv\Scripts\python.exe" "%~dp0OpenJarvis-Local.py"
if errorlevel 1 pause
