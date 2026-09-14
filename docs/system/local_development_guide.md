# KapuLetu Local Development Guide

This guide will walk you through setting up your local development environment for the KapuLetu Backend. You will run a local PostgreSQL database using Docker and start the FastAPI local server with full logging enabled.

## Prerequisites
1. **Docker**: Ensure Docker and Docker Compose are installed and running on your machine.
2. **Python 3.9+**: Ensure Python is installed.

---

## 1. Python Environment Setup
Before running the application, you need to create an isolated Python virtual environment and install the required dependencies.

Open your terminal in the `kapuletu-backend` directory and run:

**On Windows (Command Prompt / PowerShell):**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Start the Local PostgreSQL Database
We have a pre-configured `docker-compose.yml` file that spins up a local PostgreSQL database container named `kapuletu_db`.

Open your terminal in the `kapuletu-backend` directory and run:
```bash
docker-compose up -d
```
* Note: The `-d` flag runs the container in the background (detached mode).
* To stop the database later, you can run `docker-compose down`.

**Database Credentials:**
* **Host:** `localhost`
* **Port:** `5433` (Mapped from internal port 5432)
* **User:** `postgres`
* **Password:** `password`
* **Database Name:** `kapuletu`

---

## 3. Set Up Your Local Environment Variables
Create a `.env` file in the root of your `kapuletu-backend` directory (if you haven't already). It should contain your database URL and API keys:

```env
# Database configuration
DATABASE_URL=postgresql://postgres:password@localhost:5433/kapuletu

# Authentication & JWT
JWT_SECRET_KEY=your-local-super-secret-key-change-me

# External APIs (Meta & Africa's Talking)
# You can leave these blank or invalid while testing locally if you just want to read the OTPs from the console!
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
AT_USERNAME=sandbox
AT_API_KEY=
AT_SENDER_ID=
RESEND_API_KEY=
```

---

## 4. Run Database Migrations
Before starting the server, ensure your database schema is up to date by running the Alembic migrations:
```bash
alembic upgrade head
```

---

## 5. Start the Local Server
Your `local_server.py` is configured to run a fully functional FastAPI web server that maps all your endpoints. I have recently updated it to ensure that all `logger.info()` logs (including your generated OTPs) are printed beautifully to your terminal.

Start the server by running the python file directly:
```bash
python local_server.py
```
* Note: The `local_server.py` file is pre-configured to run `uvicorn` under the hood.

---

## 6. Testing the Application
Once the server is running, you can access the local Developer Portal and API Documentation:
* **Developer Portal:** [http://localhost:8000/](http://localhost:8000/)
* **Interactive API Explorer (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)

### How to test OTPs without paying for SMS/WhatsApp
When you trigger an endpoint that generates an OTP (like `/auth/register` or `/auth/verify-email/request`), the backend will attempt to send the message. However, the exact 6-digit OTP is also securely logged to your local terminal running the server!

Look at the console where your server is running, and you will see:
```text
INFO:     ====== OTP GENERATED ======
INFO:     Identifier: +254714703374
INFO:     Code: 280417
INFO:     Purpose: registration
INFO:     ===========================
```
You can safely copy this code from the terminal and use it to test your `/auth/verify-account` endpoint directly in the Swagger UI.
