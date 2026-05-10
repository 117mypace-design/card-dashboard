@echo off
setlocal

cd /d "%~dp0"

set "REPO_URL=%~1"
if not defined REPO_URL (
  set /p REPO_URL=GitHub repository URL:
)

if not defined REPO_URL (
  echo Repository URL is required.
  exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "%REPO_URL%"
) else (
  git remote set-url origin "%REPO_URL%"
)

git push -u origin main
if errorlevel 1 (
  echo Push failed.
  exit /b 1
)

echo Remote configured and main branch pushed.
