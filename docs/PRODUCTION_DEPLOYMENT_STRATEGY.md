# Professional Production Deployment Strategy (AWS)

This document outlines the strategy for deploying the KapuLetu Backend to a production-grade AWS environment.

---

## 🏗️ 1. Infrastructure Management (Serverless Framework)

We use the **Serverless Framework** as our Infrastructure-as-Code (IaC) tool. To maintain a professional setup, we separate configurations by **Stage** (dev, staging, prod).

### Multi-Stage Configuration
In `serverless.yml`, we use variables to dynamically configure resources:
```yaml
service: kapuletu-backend

provider:
  name: aws
  stage: ${opt:stage, 'dev'}
  region: us-east-1
  # Environment-specific variables
  environment:
    DATABASE_URL: ${ssm:/kapuletu/${self:provider.stage}/DATABASE_URL}
    SECRET_KEY: ${ssm:/kapuletu/${self:provider.stage}/SECRET_KEY}
```

---

## 🛠️ 2. CI/CD Pipeline (GitHub Actions)

A professional setup requires automated deployments to prevent human error.

### Pipeline Workflow:
1.  **Quality Gate**: Every Pull Request triggers `ruff` (linting) and `pytest` (unit tests).
2.  **Deployment Trigger**: 
    - Merges to `dev` branch deploy to the **Staging** environment.
    - Tagged releases (e.g., `v1.0.0`) deploy to **Production**.
3.  **Authentication**: Uses **OpenID Connect (OIDC)**. No AWS keys are stored in GitHub.

---

## 🔐 3. Secret Management (AWS SSM / Secrets Manager)

**Never hardcode credentials.** 
- **Development/Local**: Use `.env` (ignored by git).
- **Production**: Use **AWS Systems Manager (SSM) Parameter Store** or **AWS Secrets Manager**.

---

## 🗄️ 4. Production Database (Amazon RDS)

While local dev uses Docker, production uses **Amazon RDS for PostgreSQL**.

### Professional Setup Requirements:
- **Multi-AZ Deployment**: Ensures high availability.
- **VPC Isolation**: Database in a Private Subnet.
- **IAM Database Authentication**: Secure passwordless connections.
- **Automated Backups**: Enabled for disaster recovery.

---

## 📜 5. Immutable Ledger (Amazon QLDB)

The "Financial Truth" is stored in QLDB.
- **Ledger Name**: `kapuletu-ledger-prod`
- **Permissions**: Lambda functions must have `qldb:SendCommand` permissions.

---

## 📈 6. Monitoring & Observability

- **Amazon CloudWatch**:
  - **Logs**: Structured JSON logging.
  - **Metrics**: Track `Duration`, `Errors`, and `Throttles`.
- **AWS X-Ray**: Enabled for distributed tracing.

---

## 🛡️ 8. Security Best Practices
- **Least Privilege**: Dedicated IAM roles for each function.
- **Dependency Scanning**: Continuous vulnerability checks.
- **API Keys**: Throttling and monitoring via API Gateway.
