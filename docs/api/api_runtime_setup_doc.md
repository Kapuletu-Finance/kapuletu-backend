# API Runtime Documentation (Local Development)

This document explains how to run the KapuLetu Backend locally so that the endpoints are active and ready to receive requests.

---

## 🚀 Running the Local API Server

Since the application is designed as a set of AWS Lambda handlers, we use a **FastAPI Bridge** (`local_server.py`) to expose these handlers as a standard HTTP API during local development.

### 1. Prerequisites
- Complete the [Local Database Setup](LOCAL_DATABASE_SETUP.md).
- Ensure the virtual environment is active and dependencies are installed.

### 2. Start the Server
Run the following command from the project root:
```powershell
$env:PYTHONPATH="."
.\venv\Scripts\python local_server.py
```
By default, the server will start at: `http://127.0.0.1:8000`

---

## 🛠️ Available Endpoints

The local server maps HTTP routes to the corresponding Lambda handlers:

| Endpoint | Method | Handler | Purpose |
| :--- | :--- | :--- | :--- |
| `/ingestion` | `POST` | `ingestion/handler.py` | Twilio Webhook (Message processing) |
| `/approval` | `POST` | `approval/handler.py` | Transaction approval logic |
| `/reporting` | `POST` | `reporting/handler.py` | Generate financial reports |
| `/members` | `ANY` | `members/handler.py` | Member CRUD operations |
| `/campaigns` | `ANY` | `campaigns/handler.py` | Campaign management |

---

## 📡 Interactive Documentation (Swagger UI)

One of the benefits of using the FastAPI bridge is that it automatically generates an interactive documentation page.

- **URL**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Features**: You can test endpoints directly from your browser, view request schemas, and see example responses.

---

## 🧩 How the Bridge Works (`local_server.py`)

The `local_server.py` script performs **Event Emulation**:

1.  It intercepts an incoming HTTP request via FastAPI.
2.  It converts the request data (Body, Headers, Query Params) into the **AWS Lambda Event** format.
3.  It calls the specific `handler(event, context)` function for the requested service.
4.  It takes the dictionary returned by the handler (containing `statusCode` and `body`) and converts it back into a standard FastAPI `Response`.

This allows you to test the exact logic that will run in production on AWS Lambda without actually deploying to the cloud.
