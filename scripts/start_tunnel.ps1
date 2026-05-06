# KapuLetu Webhook Tunneling Script
# This script exposes your local port 8000 to the internet via ngrok

$PORT = 8000
$NGROK_COMMAND = "npx ngrok http $PORT"

Clear-Host
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   KapuLetu External Webhook Tunnel (ngrok)         " -ForegroundColor White -BackgroundColor Blue
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Targeting: http://localhost:$PORT" -ForegroundColor Gray
Write-Host "Status:    Waiting for tunnel initiation..." -ForegroundColor Yellow
Write-Host ""
Write-Host "[!] Important: Ensure local_server.py is running in another terminal." -ForegroundColor DarkYellow
Write-Host "[!] Dashboard: http://localhost:4040 (view request history here)" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "Starting tunnel via npx..." -ForegroundColor Gray

# Execute ngrok
Invoke-Expression $NGROK_COMMAND
