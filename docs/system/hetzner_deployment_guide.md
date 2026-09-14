# KapuLetu: Hetzner Deployment Guide

This guide explains how to deploy the KapuLetu backend to a Hetzner Cloud Virtual Private Server (VPS) using Docker Compose. This deployment strategy runs entirely independently of your AWS infrastructure.

## 1. Initial Server Setup (Step-by-Step for Beginners)

If you have never used Hetzner before, follow these exact steps to get your server running:

**Step 1: Create an Account and Project**
1. Go to [hetzner.com](https://www.hetzner.com/) and create a "Cloud" account.
2. Once logged into the Cloud Console (console.hetzner.cloud), create a new **Project** (e.g., "KapuLetu Prod").
3. Click into the project and click the big red **Add Server** button.

**Step 2: Configure Your Server**
1. **Location:** Choose the data center closest to your users (e.g., Falkenstein, Germany is usually cheapest/best for Africa/Europe routing if they don't have a local one).
2. **Image:** Select **Ubuntu** (the latest version, e.g., 24.04 or 22.04).
3. **Type:** Choose **Shared vCPU** -> **x86** -> **CX22** (2 vCPUs, 4GB RAM). This is usually ~€3.79/month and is incredibly powerful for FastAPI.
4. **Networking:** Leave the default Public IPv4 enabled.
5. **SSH Keys:** Click "Add SSH Key". If you don't have one on your Windows machine, open PowerShell and type `ssh-keygen`. Copy the contents of `C:\Users\josep\.ssh\id_rsa.pub` and paste it into Hetzner. This allows you to securely log in without a password.
6. **Name:** Name your server `kapuletu-prod-node`.
7. Click **Create & Buy now**.

**Step 3: SSH Into Your Server**
1. Wait 30 seconds for the server to spin up. Hetzner will give you an **IP Address** (e.g., `198.51.100.1`).
2. Open PowerShell on your Windows machine and run:
   ```bash
   ssh root@<YOUR_HETZNER_IP_ADDRESS>
   ```
3. Type `yes` if it asks to confirm the fingerprint. You are now inside your server's terminal!

**Step 4: Install Docker & Git**
Now that you are inside the Ubuntu server, run these commands to install the required tools:
```bash
# Update the server's package list
apt-get update

# Install Docker, Docker Compose, and Git
apt-get install -y docker.io docker-compose git

# Verify Docker is running
systemctl enable docker
systemctl start docker
```
## 2. Clone the Repository
Clone your code repository onto the server:
```bash
git clone https://github.com/your-username/kapuletu-backend.git
cd kapuletu-backend
```

## 3. Set up the Environment File
Create a `.env` file on the server. Do **not** commit this file to GitHub!
```bash
nano .env
```
Paste in your production credentials:
```env
# Database connection (Connects directly over Docker's internal network)
DATABASE_URL=postgresql://postgres:password@db:5432/kapuletu

# Security
JWT_SECRET_KEY=your_super_secret_production_key_here

# External Services
RESEND_API_KEY=your_resend_api_key
AT_USERNAME=your_africas_talking_username
AT_API_KEY=your_africas_talking_api_key
AT_SENDER_ID=your_sender_id
```

## 4. Boot the Server!
With the `.env` file created, you simply tell Docker Compose to build the API using our dedicated `Dockerfile.hetzner` and start both the API and Database containers in the background (`-d`):

```bash
sudo docker-compose -f docker-compose.hetzner.yml up -d --build
```

### What happens now?
1. Docker pulls the PostgreSQL database image and starts it.
2. Docker builds your FastAPI code into an ultra-fast Python container.
3. It binds port `80` on your server directly to the API container.
4. You can immediately access your live production server by navigating to `http://<YOUR_HETZNER_IP_ADDRESS>`.

## 5. Running Migrations
Because your database is brand new, you need to run Alembic to generate the tables. You can execute this command directly *inside* the running API container:

```bash
sudo docker exec kapuletu_api_prod alembic upgrade head
```
Your database is now fully initialized and ready to accept live user traffic!

---
*Note: Your AWS deployments remain untouched. They will continue to use the default `Dockerfile` and `docker-compose.yml`.*
