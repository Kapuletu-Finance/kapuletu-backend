Core Compute & Routing
AWS Lambda (1): Your entire backend runs here. It runs your Docker container equipped with Python 3.11, FastAPI, and heavy data libraries (spaCy, pandas).
Amazon API Gateway (1): The "Front Door." It provides the public HTTP endpoints and acts as a proxy, routing all incoming requests (from React, Twilio, M-Pesa) directly to your Lambda.
Amazon Elastic Container Registry - ECR (1): This is your private Docker Hub. The GitHub pipeline pushes your built backend image here so Lambda can run it.
Database & Storage
Amazon RDS - PostgreSQL (1): Your operational database. We are using a db.t3.micro instance. It holds your users, ledgers, pending transactions, and groups securely.
Amazon S3 (1 Bucket): Object storage. Used to store generated application assets, like your exported Excel summaries and PDF reports.
Security & Authentication
Amazon Cognito (1 User Pool & 1 App Client): Your authentication engine. It handles user registration, stores passwords securely, manages JWT tokens, and sends SMS verification codes.
AWS Secrets Manager (2+ Secrets): The vault. It securely encrypts and stores your database passwords, Twilio API keys, and M-Pesa credentials so they are never hardcoded.
AWS IAM (Multiple Roles): The permission boundary. This includes the OIDC Role (allowing GitHub Actions to deploy without storing long-lived keys) and the Lambda Execution Role (giving your code permission to talk to the database).
Networking & DNS
Amazon VPC (1): Your private cloud boundary.
Subnets (4): 2 Public Subnets (to route internet traffic) and 2 Private Subnets (where your RDS database and Lambda live safely away from hackers).
NAT Gateway (1): The bridge. It allows your Lambda in the private subnet to reach out to the public internet (e.g., to send a message via Twilio) without letting the public internet reach into your Lambda directly.
Amazon Route53 & ACM (1 each): Maps your custom domain (dev-api.kapuletu.co.ke) to the API Gateway and provides a free, auto-renewing SSL certificate.
Monitoring
Amazon CloudWatch (1 setup): The logging engine. It automatically records every error, print statement, and performance metric from your API Gateway and Lambda for easy debugging.