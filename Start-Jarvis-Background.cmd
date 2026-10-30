@echo off
setlocal
start "" /b "%~dp0OpenJarvis\.venv\Scripts\pythonw.exe" "%~dp0jarvis_background.py"
