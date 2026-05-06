# Local Execution Guide (One-Click Setup)

This document contains all the commands required to get the KapuLetu Backend up and running on your local machine for development and testing.

---

## 🛠️ Step 1: Environment & Dependencies
Initialize your Python environment and install all necessary packages.

```powershell
# Create virtual environment
python -m venv venv

# Activate environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🏗️ Step 2: Infrastructure (Docker)
Start the PostgreSQL database container.

```powershell
# Start the database in detached mode
docker-compose up -d
```
*Note: The database runs on port **5433** to avoid host conflicts.*

---

## 🗄️ Step 3: Database Preparation
Apply migrations to create tables and seed initial data (Plans and Admin).

```powershell
# Apply Alembic migrations
.\venv\Scripts\python scripts\migrate.py

# Seed initial system data
$env:PYTHONPATH="."
.\venv\Scripts\python scripts\seed_data.py
```

---

## 🚀 Step 4: Start the API Server
Run the FastAPI bridge to activate the endpoints.

```powershell
# Set PYTHONPATH and start the server
$env:PYTHONPATH="."
.\venv\Scripts\python local_server.py
```
*The server will be active at: **http://127.0.0.1:8000***

---

## 🧪 Step 5: Verify the Setup
Run this command in a new PowerShell window to test the ingestion endpoint:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingestion" -Method Post -Body @{
    Body = "KES 1500 from Jane Doe for Welfare"
    From = "+254700000000"
    MessageSid = "SM_TEST_123"
} -ContentType "application/x-www-form-urlencoded"
```

---

## 📡 Interactive Docs
Once the server is running, visit:
**[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**
to see the full API specification and test individual endpoints.
