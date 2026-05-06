# Code-to-Cloud: Hosting and Deployment Guide

This guide explains exactly how the code we are writing locally will end up hosted on AWS, how the environments (Dev, Staging, Production) are organized, and the step-by-step journey from a developer's machine to the live internet.

---

## 1. How Hosting Will Happen (Serverless AWS)

Unlike traditional hosting where you rent a server (like a VPS or EC2 instance) and keep it running 24/7, **KapuLetu uses a Serverless Hosting Model on AWS**. 

Here is what that means:
* **AWS API Gateway:** Acts as the "front door". It receives HTTP requests (e.g., from your frontend or mobile app) and routes them to our backend logic.
* **AWS Lambda:** This is where our Python codebase actually runs. Instead of a running server, AWS takes our code, spins up a small micro-environment *only when a request comes in*, runs the function (e.g., `services/ingestion/handler.py`), returns the response, and then spins down. 
* **Benefits:** You only pay for exactly what you use. If no one uses the app at 2 AM, your hosting cost for compute is $0.

---

## 2. The Journey: From Local Code to AWS via GitHub

The process of getting the code from your local computer into AWS is fully automated. Here is the path it takes:

### Step A: Local Development
You write code, test it locally, and create a commit.

### Step B: Push to GitHub
You push your changes to a specific branch on GitHub (e.g., you push a feature to `dev`).

### Step C: GitHub Actions (The Robot)
We will set up an automated script in GitHub called **GitHub Actions**. As soon as it sees new code arrive on the branch, the robot wakes up and does the following:
1. **Checks the code:** Runs tests (`pytest`) and checks formatting (`ruff`) to make sure the code isn't broken.
2. **Logs into AWS:** It securely authenticates with your AWS account using a mechanism called OIDC (so no permanent passwords are saved in GitHub).
3. **Packages the App:** It zips up all your Python files, the `serverless.yml` configuration, and any required libraries.
4. **Deploys to AWS:** It runs the command `serverless deploy`. This tells AWS to update the Lambda functions and API Gateway with the new code.

---

## 3. Organizing the Codebase: Dev, Staging, and Production

To ensure we never break the live app while building new features, we use a strict "3-Environment" strategy. Both GitHub and AWS mirror each other perfectly.

### Environment 1: Development (`dev`)
* **GitHub Branch:** `dev`
* **AWS Environment:** "Dev AWS Account / Dev Stage"
* **Purpose:** This is the sandbox. All new features are merged here first. It is used by the developers to test if everything works together.
* **Database:** Connects to a `dev` PostgreSQL database and a `dev` QLDB ledger. Fake data is used here.

### Environment 2: Staging (`staging`)
* **GitHub Branch:** `staging`
* **AWS Environment:** "Staging AWS Account / Staging Stage"
* **Purpose:** This is the exact replica of Production. Once a feature works in Dev, the code is moved to the Staging branch. This is where Quality Assurance (QA) testing happens, or where clients test the app before it goes live.
* **Database:** Connects to a `staging` database. Data here looks very real but is not actual customer data.

### Environment 3: Production (`production` or `main`)
* **GitHub Branch:** `main` (or `production`)
* **AWS Environment:** "Production AWS Account / Prod Stage"
* **Purpose:** The live application used by real paying users. 
* **Database:** The live, highly-secured PostgreSQL and QLDB databases.
* **Rule:** Nobody pushes code directly to this branch. Code only gets here after passing through Dev and Staging.

---

## 4. How the Services Will Work Together

Once deployed, the ecosystem functions autonomously:

1. **The Request:** A user submits a transaction on the frontend. The frontend sends an HTTP POST request to an AWS API Gateway URL (e.g., `https://api.kapuletu.com/ingestion`).
2. **The Logic:** API Gateway triggers the specific AWS Lambda function (defined in `serverless.yml`). The Lambda executes the Python code.
3. **The Data:** The Lambda function securely fetches its environment variables (like `DATABASE_URL`) from AWS Parameter Store, connects to the RDS PostgreSQL database to update balances, and writes the immutable ledger record to Amazon QLDB.
4. **The Response:** Lambda sends a "Success" response back to the frontend.

---

## 5. What We Are Setting Up After Coding Here

Once we finish writing the core Python codebase, here is the immediate roadmap of what needs to be set up:

1. **AWS Account Setup:** 
   * Create the AWS account.
   * Set up an IAM Role that GitHub Actions can use.
2. **Database Provisioning:** 
   * Create an Amazon RDS PostgreSQL database (for dev/staging/prod).
   * Create the Amazon QLDB Ledgers.
3. **GitHub Configuration:** 
   * Add the AWS Connection details as "Secrets" inside the GitHub repository settings.
   * Create the `.github/workflows/deploy.yml` file in this codebase to activate the CI/CD pipeline.
4. **The First Deployment:** 
   * We will merge our code into the `dev` branch on GitHub.
   * We will watch the GitHub Actions tab automatically build and push the code to AWS.
   * We will test the live AWS API Gateway URLs (e.g., via Postman) to confirm the cloud setup matches our local tests.
