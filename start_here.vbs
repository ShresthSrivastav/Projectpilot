Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\shres\Desktop\ProjectPilot"
WshShell.Run "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000", 0, False
WScript.Sleep 3000
WshShell.Run "streamlit run frontend/app.py --server.port 8501 --server.headless true", 0, False
