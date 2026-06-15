$env:PYTHONPATH = "C:\Users\shres\Desktop\autodev-ai-v4.1"
$logDir = "C:\Users\shres\Desktop\autodev-ai-v4.1"
$p1 = Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory "C:\Users\shres\Desktop\autodev-ai-v4.1" -RedirectStandardOutput "$logDir\backend.log" -RedirectStandardError "$logDir\backend_err.log" -PassThru
Start-Sleep -Seconds 1
$p2 = Start-Process -NoNewWindow -FilePath "streamlit" -ArgumentList "run frontend/app.py --server.port 8501" -WorkingDirectory "C:\Users\shres\Desktop\autodev-ai-v4.1" -RedirectStandardOutput "$logDir\frontend.log" -RedirectStandardError "$logDir\frontend_err.log" -PassThru
Write-Host "Backend PID: $($p1.Id)" | Out-File -FilePath "$logDir\startup_result.txt"
Write-Host "Frontend PID: $($p2.Id)" | Out-File -FilePath "$logDir\startup_result.txt" -Append
