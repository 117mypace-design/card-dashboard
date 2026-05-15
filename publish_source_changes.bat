@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
cd /d %~dp0

git config --global --add safe.directory C:/card-tracker >nul 2>nul

set "CHANGED_FILES="
for %%F in (
  deck_types.json
  meta_cards.json
  card_image_cache.json
  seasons.json
  season_utils.py
  update_expansion_seasons.py
  find_events_v2.py
  fetch_results_s4.py
  generate_report_local_alltrend.py
  build_dashboard_multipage_fullperiod_styled.py
  .github/workflows/update-dashboard.yml
  README.md
  requirements.txt
  .gitignore
  publish_source_changes.bat
  publish_deck_types.bat
  publish_meta_cards.bat
  publish_seasons.bat
  run_fetch_report_dashboard.bat
  run_report_dashboard.bat
  connect_github_remote.bat
) do (
  git diff --quiet -- "%%F"
  if errorlevel 1 set "CHANGED_FILES=!CHANGED_FILES! %%F"
)

if not defined CHANGED_FILES (
  echo No source/config changes to publish.
  pause
  exit /b 0
)

set "COMMIT_MSG=%~1"
if not defined COMMIT_MSG (
  set "ONE_FILE="
  for %%F in (%CHANGED_FILES%) do (
    if defined ONE_FILE (
      set "ONE_FILE=MULTI"
    ) else (
      set "ONE_FILE=%%F"
    )
  )
  if /I "!ONE_FILE!"=="deck_types.json" set "COMMIT_MSG=chore: update deck types"
  if /I "!ONE_FILE!"=="meta_cards.json" set "COMMIT_MSG=chore: update meta cards"
  if /I "!ONE_FILE!"=="card_image_cache.json" set "COMMIT_MSG=chore: update card image cache"
  if /I "!ONE_FILE!"=="seasons.json" set "COMMIT_MSG=chore: update seasons"
  if not defined COMMIT_MSG (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd HH:mm')"`) do set "NOW=%%I"
    set "COMMIT_MSG=chore: update source files !NOW!"
  )
)

echo [1/5] Staging source files...
git add -- ^
  deck_types.json ^
  meta_cards.json ^
  card_image_cache.json ^
  seasons.json ^
  season_utils.py ^
  update_expansion_seasons.py ^
  find_events_v2.py ^
  fetch_results_s4.py ^
  generate_report_local_alltrend.py ^
  build_dashboard_multipage_fullperiod_styled.py ^
  .github/workflows/update-dashboard.yml ^
  README.md ^
  requirements.txt ^
  .gitignore ^
  publish_source_changes.bat ^
  publish_deck_types.bat ^
  publish_meta_cards.bat ^
  publish_seasons.bat ^
  run_fetch_report_dashboard.bat ^
  run_report_dashboard.bat ^
  connect_github_remote.bat ^
  work_shortcuts
if errorlevel 1 (
  echo ERROR: git add failed.
  pause
  exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
  rem there are staged changes
) else (
  echo No source/config changes to publish.
  pause
  exit /b 0
)

echo.
echo [2/5] Committing...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
  echo ERROR: git commit failed.
  pause
  exit /b 1
)

echo.
echo [3/5] Rebasing on latest GitHub main...
git pull --rebase origin main
if errorlevel 1 (
  echo ERROR: git pull --rebase failed.
  echo Resolve the message shown above, then try again.
  pause
  exit /b 1
)

echo.
echo [4/5] Pushing to GitHub...
git push
if errorlevel 1 (
  echo ERROR: git push failed.
  pause
  exit /b 1
)

echo.
echo [5/5] Done.
echo.
echo Usual setting/code changes such as deck_types.json trigger GitHub auto update after push.
echo If you changed seasons.json, season_utils.py, update_expansion_seasons.py, find_events_v2.py, or fetch_results_s4.py, run Update Dashboard manually with fetch_data = true when you need a fresh fetch immediately.
pause
exit /b 0
