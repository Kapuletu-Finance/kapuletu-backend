# CI/CD Technical Documentation

This document describes the technical implementation and configuration of the CI/CD pipeline for the KapuLetu Backend.

## 🏗️ Architecture
The pipeline is built with **GitHub Actions** and interacts with **AWS Lambda** via the **Serverless Framework**.

## 🌳 Branching Strategy
| Branch | Environment | Stage | Use Case |
| :--- | :--- | :--- | :--- |
| `dev` | Development | `dev` | Active development and integration testing. |
| `staging` | Staging | `staging` | Pre-production validation and UAT. |
| `production` | Production | `prod` | Live production environment. |
| `feature/*` | CI Only | N/A | Feature development; runs tests but no deployment. |

## 🔐 Security & Authentication
The pipeline uses **AWS OIDC (OpenID Connect)**. This eliminates the need for long-lived AWS Access Keys.

### Prerequisites
1. **OIDC Provider**: Ensure an OIDC provider for GitHub is created in your AWS account.
2. **IAM Roles**: Create the following roles with trust relationships allowing GitHub Actions to assume them:
   - `kapuletu-ci-cd-role-dev`
   - `kapuletu-ci-cd-role-staging`
   - `kapuletu-ci-cd-role-prod`

### Required GitHub Secrets
| Secret Name | Description |
| :--- | :--- |
| `AWS_ACCOUNT_ID` | Your 12-digit AWS Account ID. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `SECRET_KEY` | Application security key. |
| `QLDB_LEDGER_NAME` | Name of the QLDB ledger. |
| `TWILIO_SECRET` | Twilio webhook secret. |

> [!NOTE]
> It is recommended to use **GitHub Environments** to manage these secrets per stage.

## 🛠️ Pipeline Stages
Each deployment workflow follows these steps:
1. **Checkout**: Pulls the latest code from the repository.
2. **Setup Python**: Installs Python 3.11 and configures caching for `pip`.
3. **Linting**: Runs `ruff check .` to enforce style and quality rules.
4. **Testing**: Executes `pytest` to ensure logic correctness.
5. **Node.js Setup**: Prepares the environment for the Serverless Framework.
6. **AWS Auth**: Configures credentials via OIDC.
7. **Package Validation**: Runs `serverless package` to verify the bundle.
8. **Deployment**: Executes `serverless deploy` to push changes to AWS.

## ⌨️ Manual Control
All workflows include a `workflow_dispatch` trigger, allowing you to manually trigger a deployment from the GitHub Actions UI.
