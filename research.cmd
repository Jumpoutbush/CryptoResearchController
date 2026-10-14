@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if defined CRC_PYTHON (
  "%CRC_PYTHON%" "%~dp0research.py" %*
  exit /b
)
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0research.py" %*
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0research.py" %*
  exit /b
)
python "%~dp0research.py" %*
exit /b
