# ResuMate AI — one-click dev starter.
# Frees ports 8000/5173 if stale processes hold them, then launches the
# backend and frontend each in its own terminal window.
# Stop the servers by simply closing the two windows.
$root = $PSScriptRoot

foreach ($port in 8000, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -Confirm:$false
            Write-Host "Freed port $port (killed PID $($conn.OwningProcess))"
        } catch {}
    }
}

# use the venv's python directly — no Activate.ps1, so execution policy never matters
Start-Process powershell -ArgumentList @(
    '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
    "cd '$root\backend'; & '.\.venv\Scripts\python.exe' -m uvicorn main:app --port 8000"
) -WindowStyle Normal

Start-Process powershell -ArgumentList @(
    '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
    "cd '$root\frontend'; npm run dev"
) -WindowStyle Normal

Write-Host ""
Write-Host "Backend  -> http://localhost:8000  (API docs: /docs)"
Write-Host "Frontend -> http://localhost:5173   <- use THIS address, not 5174/5175"
Write-Host "Two terminal windows opened - close them to stop the servers."
