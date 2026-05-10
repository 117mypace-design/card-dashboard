@echo off
chcp 65001 > nul
setlocal
set PYTHONIOENCODING=utf-8
cd /d %~dp0

if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
for /f "delims=" %%I in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
    for /f "delims=" %%I in ('where py 2^>nul') do if not defined PYTHON_EXE (
        set "PYTHON_EXE=%%I"
        set "PYTHON_ARGS=-3"
    )
)
if not defined PYTHON_EXE if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
if not defined PYTHON_EXE (
    echo ERROR: Python runtime not found.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE% %PYTHON_ARGS%
echo.

echo [1/2] Generating report and full-period JSON...
if defined PYTHON_ARGS (
    "%PYTHON_EXE%" %PYTHON_ARGS% generate_report_local_alltrend.py
) else (
    "%PYTHON_EXE%" generate_report_local_alltrend.py
)
if errorlevel 1 (
    echo ERROR: generate_report_local_alltrend.py failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

set "FULLPERIOD_JSON="
for /f "delims=" %%I in ('dir /b /a-d /o-d "%~dp0reports\*_fullperiod.json"') do if not defined FULLPERIOD_JSON set "FULLPERIOD_JSON=%~dp0reports\%%I"
if not defined FULLPERIOD_JSON (
    echo ERROR: Could not find reports\*_fullperiod.json.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo [2/2] Rebuilding dashboard site...
if defined PYTHON_ARGS (
    "%PYTHON_EXE%" %PYTHON_ARGS% build_dashboard_multipage_fullperiod_styled.py "%FULLPERIOD_JSON%" "%~dp0site_fullperiod"
) else (
    "%PYTHON_EXE%" build_dashboard_multipage_fullperiod_styled.py "%FULLPERIOD_JSON%" "%~dp0site_fullperiod"
)
if errorlevel 1 (
    echo ERROR: build_dashboard_multipage_fullperiod_styled.py failed.
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo Done!
echo Report JSON: %FULLPERIOD_JSON%
echo Dashboard: %~dp0site_fullperiod
if not defined NO_PAUSE pause
exit /b 0
