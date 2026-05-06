# AWS Serverless Architecture Documentation

This document explains how the KapuLetu Backend operates in the AWS production environment. 

> [!IMPORTANT]
> While we use a FastAPI bridge for **local development**, the production environment on AWS is **fully serverless** and does NOT use FastAPI. Instead, it relies on individual AWS Lambda functions triggered by API Gateway.

---

## 🏗️ 1. Infrastructure Overview

The application follows an **Event-Driven Serverless Architecture** managed by the **Serverless Framework** (`serverless.yml`).

### Core Components:
- **AWS Lambda**: The compute layer. Each folder in `services/` corresponds to a separate Lambda function.
- **Amazon API Gateway**: The routing layer. It receives HTTP requests and invokes the correct Lambda function.
- **Amazon RDS (PostgreSQL)**: The relational database for operational state.
- **Amazon QLDB**: The immutable ledger for finalized financial records.
- **Twilio**: The external event source that triggers the `ingestion` service.

---

## ⚡ 2. How it Works on AWS

When the application is deployed to AWS (using `serverless deploy`), the following occurs:

### Request Flow:
1.  **Incoming Trigger**: A user sends a WhatsApp/SMS message via Twilio.
2.  **API Gateway**: Twilio hits a POST endpoint on API Gateway (e.g., `https://api.kapuletu.com/ingestion`).
3.  **Lambda Invocation**: API Gateway packs the HTTP request into a JSON object called an **Event** and invokes the `ingestion` Lambda function.
4.  **Handler Execution**: The Lambda runtime calls the `handler(event, context)` function in `services/ingestion/handler.py`.
5.  **Persistence**: The handler processes the message and saves it to **Amazon RDS**.
6.  **Response**: The handler returns a dictionary (JSON), which API Gateway converts back into an HTTP response for Twilio.

---

## 📂 3. Service Decomposition (Micro-functions)

Instead of one large "monolith" app, each service is its own independent function:

| Service | AWS Resource | Trigger |
| :--- | :--- | :--- |
| **Ingestion** | `kapuletu-ingestion` Lambda | POST `/ingestion` |
| **Approval** | `kapuletu-approval` Lambda | POST `/approval` |
| **Reporting** | `kapuletu-reporting` Lambda | POST `/reporting` |
| **Members** | `kapuletu-members` Lambda | ANY `/members` |
| **Campaigns** | `kapuletu-campaigns` Lambda | ANY `/campaigns` |

---

## 🔧 4. Deployment Logic (`serverless.yml`)

The `serverless.yml` file is the blueprint for the entire AWS infrastructure. It defines:

- **Runtime**: Python 3.11
- **Region**: `us-east-1`
- **Environment Variables**: Injected into Lambda functions (e.g., `DATABASE_URL`, `SECRET_KEY`).
- **Events**: Maps HTTP paths/methods to specific Python handlers.

```yaml
functions:
  ingestion:
    handler: services/ingestion/handler.handler
    events:
      - http:
          path: ingestion
          method: post
```

---

## 💡 5. Local vs. Production Comparison

It is critical to distinguish between the two environments:

| Feature | Local Development | AWS Production |
| :--- | :--- | :--- |
| **Runtime** | `local_server.py` (FastAPI) | AWS Lambda (Raw Handlers) |
| **Routing** | FastAPI Router | API Gateway |
| **Environment** | Local Python Process | Isolated Firecracker MicroVMs |
| **Database** | Docker (PostgreSQL 15) | Amazon RDS (PostgreSQL) |
| **Scalability** | Single Process | Auto-scaling to thousands of concurrent calls |

---

## 🔐 6. Security & Scaling
- **Concurrency**: AWS Lambda scales automatically. Each new incoming request spins up a new instance of your code.
- **IAM Roles**: Each Lambda function is assigned a specific "Identity and Access Management" role, granting it only the permissions it needs (e.g., access to RDS but not S3).
- **Cold Starts**: The first request to a function may have a slight delay ("Cold Start"), but subsequent requests are extremely fast.
