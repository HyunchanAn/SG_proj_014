@echo off
echo ========================================================
echo SG-Adhesion Nexus Orchestrator API (Port 8024)
echo ========================================================
echo.
echo Activating Virtual Environment...
call ..\venv\Scripts\activate 2>nul
if errorlevel 1 (
    echo Venv not found, using global python.
)
echo Booting FastAPI Server...
python -m uvicorn src.main:app --host 0.0.0.0 --port 8024 --reload
pause
