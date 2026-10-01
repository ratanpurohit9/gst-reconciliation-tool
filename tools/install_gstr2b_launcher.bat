@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py install_gstr2b_launcher.py
  goto finished
)
where python >nul 2>nul
if not errorlevel 1 (
  python install_gstr2b_launcher.py
  goto finished
)
echo Python 3 was not found. Install Python 3 and run this installer again.
:finished
pause
