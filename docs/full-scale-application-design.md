# Full-Scale Application Design: Logic, Auth, and Subscriptions

To turn KapuLetu into a full-scale, production-ready SaaS application, we need to understand how the internal code logic executes, how we protect the data (Authentication), and how we make money (Subscriptions).

Here is the complete breakdown of how the entire application works together.

---

## 1. How the Code Logic Works (The Lambda Flow)

When an endpoint is hit (e.g., `POST /ingestion`), here is exactly how the code runs inside the Serverless environment:

1. **The Entry Point (`handler.py`):** 
   Every service (like `services/ingestion/`) has a `handler.py` file. This is the "front desk". Its only job is to receive the raw HTTP event from AWS API Gateway, extract the body/headers, and pass it to the core application logic.
2. **The Business Logic (`service.py`):**
   The handler passes the data to the service layer. This is where the "thinking" happens. For example, `ingestion_service.py` will take the raw SMS text, run the NLP parser to extract the amount and phone number, and validate the data.By structuring it this way, your core business logic is completely separated from the AWS infrastructure.
3. **The Database Layer (`repositories/`):**
   If the service needs to save data, it doesn't write SQL directly. It calls a Repository (e.g., `transaction_repository.py`). The repository handles the connection to PostgreSQL or QLDB.
4. **The Response:**
   The repository saves the data and returns a success object to the service. The service passes it back to the handler. The handler formats it into a standard HTTP Response (Status 200 OK) and sends it back to the user.

**Why this structure?** It keeps the code clean. If we ever change from AWS Lambda to something else, we only change the `handler.py`—the business logic and database code remain completely untouched.

---

## 2. How Authentication (Auth) Works

In a full-scale app, security is critical. We cannot allow anyone to hit our endpoints and view financial data.

### The Identity Provider
We will use a managed Identity Provider (IdP) like **AWS Cognito**, **Supabase Auth**, or **Auth0**. This handles password resets, email verifications, and secure logins, so we don't have to build that from scratch.

### The Authentication Flow:
1. **Login:** The user types their email/password on the frontend. The frontend sends this to the IdP.
2. **The JWT Token:** The IdP verifies the password and gives the frontend a **JSON Web Token (JWT)**. This token is like a digital VIP pass. Inside the token, it securely stores the User's ID and their Organization ID (Tenant ID).
3. **Hitting the API:** When the frontend wants to get the members list (`GET /members`), it attaches this JWT Token to the `Authorization` header of the HTTP request.
4. **API Gateway Validation (The Bouncer):** Before the AWS Lambda function even wakes up, AWS API Gateway inspects the token. If the token is fake or expired, it instantly rejects the request (Status 401 Unauthorized). This saves us compute costs.
5. **Multi-Tenancy (Data Isolation):** If the token is valid, the Lambda function runs. The code extracts the `Organization ID` from the token and adds `WHERE organization_id = X` to every database query. This guarantees User A can never see User B's financial records.

---

## 3. How Subscriptions Will Be Handled (Monetization)

To make KapuLetu a paid SaaS, we will integrate a payment gateway like **Stripe**. 

### The Database Setup
We will have an `organizations` table in PostgreSQL that stores the billing state:
* `subscription_tier`: 'Free', 'Pro', 'Premium'
* `subscription_status`: 'Active', 'Past_Due', 'Canceled'
* `stripe_customer_id`: 'cus_12345...'

### The Subscription Flow:
1. **Checkout:** The user clicks "Upgrade to Pro" on the frontend. They are redirected to a secure Stripe Checkout page.
2. **The Webhook Endpoint:** We will create a new Serverless endpoint in `serverless.yml` called `POST /webhooks/stripe`. 
3. **Stripe Notifies KapuLetu:** When the user pays, Stripe secretly sends an HTTP POST request to our `/webhooks/stripe` endpoint saying: *"Customer cus_12345 just paid for the Pro plan"*.
4. **Updating the Database:** Our webhook Lambda function receives this message, looks up the organization by `stripe_customer_id`, and updates their `subscription_tier` to 'Pro'.

### Enforcing the Tiers in Code
Inside our Lambda functions (e.g., `services/reporting/service.py`), we will add **Feature Flags/Guards**:
```python
# Pseudo-code Example inside a Lambda Service
def generate_pdf_report(organization_id):
    org = db.get_organization(organization_id)
    
    if org.subscription_tier == 'Free':
         raise PermissionError("PDF Reports require the Pro Plan.")
         
    # Proceed to generate PDF...
```
This ensures that users can only access the features they have paid for.

---

## 4. Summary of the Full Architecture

1. **Frontend (React/Next.js):** Displays the UI, handles logins via Identity Provider, and holds the JWT Token.
2. **API Gateway (AWS):** Validates the JWT Token and routes traffic.
3. **Compute (AWS Lambda):** Executes the Python business logic (`handler` -> `service` -> `repository`).
4. **Database (PostgreSQL & QLDB):** Stores the isolated, multi-tenant data securely.
5. **Payments (Stripe + Webhooks):** Manages recurring billing and notifies the backend when a user's subscription changes.
