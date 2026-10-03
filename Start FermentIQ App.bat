@echo off
rem Double-click to start the FermentIQ upload app in your browser. Close this window to stop it.
cd /d "%~dp0"
rem Open the browser a few seconds after the server starts.
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501
