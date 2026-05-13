@echo off
cd /d %~dp0
call "%~dp0publish_source_changes.bat" "chore: update seasons"
