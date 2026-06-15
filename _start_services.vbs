Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\shres\Desktop\autodev-ai-v4.1"
WshShell.Run "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000", 0, False
WScript.Sleep 2000
WshShell.Run "streamlit run frontend/app.py --server.port 8501", 0, False
