@echo off
title GST Tool - Build EXE
color 0B

REM ── FIX: Always run from the folder where THIS bat file lives ─────────────
cd /d "%~dp0"

echo.
echo ======================================================
echo    GST Reconciliation Tool -- Build Script FINAL
echo ======================================================
echo.

REM ── STEP 1: Check Python ──────────────────────────────
echo [1/5] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    pause & exit /b 1
)

REM ── STEP 2: Install packages ──────────────────────────
echo.
echo [2/5] Installing packages...
pip install pyinstaller streamlit pandas numpy altair xlsxwriter openpyxl reportlab --quiet

REM ── STEP 3: Create the DB file right here ────────────
echo.
echo [3/5] Creating recon_history.db ...

REM FIX: Use %~dp0 (this bat's folder) so the path is expanded by cmd.exe
REM      BEFORE Python sees it -- avoids the \b (backspace) escape bug.
REM      The r'' raw string prefix is a safety net for any backslashes.
python -c "import sqlite3; path = r'%~dp0recon_history.db'; sqlite3.connect(path).close(); print('DB created at:', path)"

REM Verify the DB was actually created before continuing
if not exist "%~dp0recon_history.db" (
    echo.
    echo ERROR: recon_history.db was NOT created. Check Python output above.
    pause & exit /b 1
)
echo DB verified OK.

REM ── STEP 4: Get Streamlit path ────────────────────────
echo.
echo [4/5] Finding Streamlit...
for /f "tokens=*" %%i in ('python -c "import streamlit, os; print(os.path.dirname(streamlit.__file__))"') do set STREAMLIT_PATH=%%i
echo Found: %STREAMLIT_PATH%

REM ── Clean old builds ─────────────────────────────────
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
if exist GSTReconciliationTool.spec del /q GSTReconciliationTool.spec

REM ── STEP 5: Build ────────────────────────────────────
echo.
echo [5/5] Building EXE (this takes 5-10 mins)...

pyinstaller --name "GSTReconciliationTool" --onedir --windowed --noconfirm ^
  --add-data "app.py;." ^
  --add-data "modules;modules" ^
  --add-data "recon_history.db;." ^
  --add-data "%STREAMLIT_PATH%;streamlit" ^
  --hidden-import "streamlit" ^
  --hidden-import "streamlit.web.cli" ^
  --hidden-import "streamlit.web.server" ^
  --hidden-import "streamlit.runtime" ^
  --hidden-import "streamlit.runtime.scriptrunner" ^
  --hidden-import "streamlit.runtime.scriptrunner.magic_funcs" ^
  --hidden-import "streamlit.components.v1" ^
  --hidden-import "altair" --hidden-import "pandas" --hidden-import "numpy" ^
  --hidden-import "openpyxl" --hidden-import "xlsxwriter" ^
  --hidden-import "reportlab" --hidden-import "reportlab.pdfgen" ^
  --hidden-import "reportlab.lib" --hidden-import "reportlab.lib.pagesizes" ^
  --hidden-import "reportlab.lib.styles" --hidden-import "reportlab.lib.units" ^
  --hidden-import "reportlab.lib.colors" --hidden-import "reportlab.lib.enums" ^
  --hidden-import "reportlab.platypus" --hidden-import "reportlab.platypus.tables" ^
  --hidden-import "reportlab.platypus.flowables" --hidden-import "reportlab.platypus.paragraph" ^
  --hidden-import "sqlite3" --hidden-import "uuid" ^
  --hidden-import "modules.license_manager" --hidden-import "modules.key_hashes" ^
  --collect-all "streamlit" --collect-all "altair" --collect-all "pandas" ^
  --collect-all "reportlab" ^
  --collect-data "streamlit" ^
  launcher.py

if %errorlevel% neq 0 (
    echo.
    echo ======================================================
    echo  BUILD FAILED.
    echo  Check the errors above for details.
    echo.
    echo  Make sure ALL files are in C:\gstbuild\ with no spaces
    echo  in the folder path, then re-run this script.
    echo ======================================================
    pause & exit /b 1
)

echo.
echo ======================================================
echo  BUILD COMPLETE!
echo  EXE folder: dist\GSTReconciliationTool\
echo.
echo  ZIP the entire dist\GSTReconciliationTool\ FOLDER
echo  and send that ZIP to clients.
echo  They extract it and run GSTReconciliationTool.exe
echo ======================================================
pause
