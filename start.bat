@echo off
cd /d "%~dp0"
echo Killing old processes...
for /f "tokens=2" %%P in ('tasklist /fi "IMAGENAME eq python.exe" /fo list ^| findstr /b "PID:"') do (
  tasklist /fi "PID eq %%P" /fi "WINDOWTITLE eq *uvicorn*" 2>nul | findstr /i "uvicorn" >nul && taskkill /f /pid %%P 2>nul
  tasklist /fi "PID eq %%P" /fi "WINDOWTITLE eq *streamlit*" 2>nul | findstr /i "streamlit" >nul && taskkill /f /pid %%P 2>nul
)
timeout /t 3 /nobreak >nul
echo Starting backend...
start /B python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
timeout /t 20 /nobreak >nul
echo Starting frontend...
start /B python -m streamlit run frontend/app.py --server.port 8501 --server.headless true
timeout /t 10 /nobreak >nul
echo.
echo ========================================
echo  ProjectPilot is running!
echo ========================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:8501
echo  API Docs: http://localhost:8000/docs
echo ========================================
