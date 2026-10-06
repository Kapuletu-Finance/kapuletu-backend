# Local Development Setup Guide for KapuLetu

To seamlessly develop and test the KapuLetu application locally without interfering with your production server or deployment containers, follow this structured guide. It ensures proper separation of your local environment from the online container configurations.

---

## 1. Database Configuration (Docker)

Your local database runs in an isolated Docker container configured through `docker-compose.yml`. This prevents any interference with your production database.

1. **Start the database:**
   Make sure Docker is running on your machine, then open your terminal at the backend root (`c:\Users\josep\kapuletu-backend`) and run:
   ```bash
   docker-compose up -d db
   ```
   *This starts a PostgreSQL container named `kapuletu_db` on port `5433` (mapped from `5432` internally).*

---

## 2. Backend Setup

The backend will run on port `8000` via FastAPI/Uvicorn. 

### A. Environment Variables (`.env`)
Ensure your backend `.env` file (`c:\Users\josep\kapuletu-backend\.env`) has the following local configurations:

```ini
# Use the local docker database (port 5433)
DATABASE_URL=postgresql://postgres:password@127.0.0.1:5433/kapuletu
APP_ENV=development
IS_LOCAL=true
DB_SSL_REQUIRED=false

# Keep other variables (AWS, AT, JWT) as they are for local testing
```
> [!IMPORTANT]
> The `IS_LOCAL=true` and `DB_SSL_REQUIRED=false` flags are crucial. They tell the backend to use local cookie settings (disabling secure-only cookies for `localhost`) and bypass SSL database checks that are only needed on the remote deployment.

### B. Migrations and Seeding
Once your database container is up, apply the latest database schemas and seed it with test accounts.

1. **Run Migrations:**
   ```bash
   alembic upgrade head
   ```

2. **Seed Local Accounts:**
   A script has been created (`seed_local.py`) to automatically generate standard test accounts. Run it using:
   ```bash
   python seed_local.py
   ```
   **Generated Accounts:**
   - **Admin:** `admin@kapuletu.local` (Password: `Password123!`)
   - **Treasurer:** `treasurer@kapuletu.local` (Password: `Password123!`)

### C. Run the Backend
Start the local server. It is hardcoded in `local_server.py` to run on `8000`.
```bash
python local_server.py
```
*API will be available at `http://localhost:8000`*

---

## 3. Frontend Setup

The Next.js frontend will run on port `3000`.

### A. Environment Variables (`.env.local`)
Create or edit `c:\Users\josep\kapuletu-frontend\.env.local` to point to the local backend:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
# Any other frontend variables
```

### B. Run the Frontend
Run the development server:
```bash
npm run dev
```
*Frontend will be available at `http://localhost:3000`*

---

## Summary of Local Architecture
- **Frontend (Next.js):** `http://localhost:3000` -> Communicates with the BFF Proxy or directly via Axios.
- **Backend (FastAPI):** `http://localhost:8000` -> Receives API requests.
- **Database (PostgreSQL via Docker):** `localhost:5433` -> Persists data locally on a Docker volume.

This setup ensures you can fully test the Auth flows, write blogs, and manage the inbox seamlessly as an Admin or Treasurer without affecting your live site or breaking the Docker build configurations for production.
