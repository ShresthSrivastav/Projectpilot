@echo off
cd /d "C:\Users\shres\Desktop\autodev-ai-v4.1"
start /B python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > backend_out.log 2> backend_err.log
timeout /t 3 /nobreak > nul
start /B streamlit run frontend/app.py --server.port 8501 > frontend_out.log 2> frontend_err.log
exit
