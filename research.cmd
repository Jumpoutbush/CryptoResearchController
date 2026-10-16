@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if defined CRC_PYTHON goto configured_python
if exist "%~dp0.venv\Scripts\python.exe" goto venv_python
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
python "%~dp0research.py" %*
exit /b %ERRORLEVEL%
:configured_python
"%CRC_PYTHON%" "%~dp0research.py" %*
exit /b %ERRORLEVEL%
:venv_python
"%~dp0.venv\Scripts\python.exe" "%~dp0research.py" %*
exit /b %ERRORLEVEL%
:python_launcher
py -3 "%~dp0research.py" %*
exit /b %ERRORLEVEL%
