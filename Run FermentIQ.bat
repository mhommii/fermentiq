@echo off
rem Double-click to check every batch-record PDF in data\private\raw and write one report per PDF.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m fermentiq
if exist "data\private\reports" start "" "data\private\reports"
pause
