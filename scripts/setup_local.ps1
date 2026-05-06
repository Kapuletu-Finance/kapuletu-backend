# KapuLetu Local Environment Setup Script
# This script automates the setup of the local database and environment.

Write-Host "🚀 Starting KapuLetu Local Setup..." -ForegroundColor Cyan

# 1. Check for Docker
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: Docker is not installed. Please install Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# 2. Start Docker Database
Write-Host "📡 Starting PostgreSQL via Docker Compose..." -ForegroundColor Yellow
docker-compose up -d

# 3. Wait for Database to be ready
Write-Host "⏳ Waiting for database to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 4. Check for Virtual Environment
if (!(Test-Path "venv")) {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    .\venv\Scripts\pip install -r requirements.txt
}

# 5. Run Migrations
Write-Host "🛠️ Running database migrations..." -ForegroundColor Yellow
.\venv\Scripts\python scripts\migrate.py

# 6. Seed Data (Optional)
if (Test-Path "scripts\seed_data.py") {
    Write-Host "🌱 Seeding initial data..." -ForegroundColor Yellow
    .\venv\Scripts\python scripts\seed_data.py
}

Write-Host "✅ Local environment is ready!" -ForegroundColor Green
Write-Host "   Database: postgresql://postgres:password@127.0.0.1:5433/kapuletu" -ForegroundColor White

Write-Host "`n🚀 To start the API server, run:" -ForegroundColor Cyan
Write-Host "   `$env:PYTHONPATH='.'; .\venv\Scripts\python local_server.py" -ForegroundColor White
Write-Host "`n📡 Once started, view the API docs at: http://127.0.0.1:8000/docs" -ForegroundColor White
