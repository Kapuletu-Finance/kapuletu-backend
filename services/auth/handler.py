import os

# Imagine we import our database connection here
# from repositories.user_repository import create_user_and_organization

from common.database import SessionLocal
from models.users import User

def post_confirmation(event, context):
    """
    AWS Cognito Post-Confirmation Trigger.
    
    This function is automatically triggered by AWS Cognito IMMEDIATELY after 
    a user successfully signs up and verifies their email.
    
    We use this to take the new User's Cognito ID and insert it into our 
    KapuLetu PostgreSQL database so we have a local record of them.
    """
    
    # 1. Extract the user details sent by Cognito
    user_attributes = event['request']['userAttributes']
    cognito_user_id = user_attributes.get('sub') # The unique Cognito ID
    email = user_attributes.get('email')
    first_name = user_attributes.get('given_name', 'User')
    last_name = user_attributes.get('family_name', '')
    phone_number = user_attributes.get('phone_number')
    
    print(f"Auth Hook Triggered: New User Confirmed. Email: {email}, ID: {cognito_user_id}")
    
    db = SessionLocal()
    try:
        # 2. Logic to insert user into PostgreSQL
        # Check if user already exists to prevent duplicate key errors
        existing_user = db.query(User).filter(User.email == email).first()
        
        if not existing_user:
            new_user = User(
                user_id=cognito_user_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number,
                role="treasurer"
            )
            db.add(new_user)
            db.commit()
            print(f"Successfully created user {email} in PostgreSQL database.")
        else:
            print(f"User {email} already exists in database. Skipping creation.")

        # 3. Send Professional Welcome Messages
        dashboard_url = os.environ.get('DASHBOARD_URL', 'https://app.kapuletu.com')
        
        # --- Send WhatsApp Welcome via Meta ---
        try:
            import json
            import urllib.request
            
            meta_token = os.environ.get('META_ACCESS_TOKEN')
            meta_phone_id = os.environ.get('META_PHONE_NUMBER_ID')
            support_phone = os.environ.get('SUPPORT_PHONE', '+254700000000')
            support_email = os.environ.get('SUPPORT_EMAIL', 'support@kapuletu.com')
            
            whatsapp_body = (
                f"WELCOME TO KAPULETU, {first_name.upper()}\n\n"
                f"Your account has been successfully verified and is now active.\n\n"
                f"Next Steps:\n"
                f"1. Access your dashboard: {dashboard_url}\n"
                f"2. Complete your organization profile.\n"
                f"3. Invite your team and start managing your finances.\n\n"
                f"KapuLetu is designed to provide structured, transparent, and trustworthy "
                f"financial management for your community treasury.\n\n"
                f"For assistance, please email {support_email} or contact our support team at {support_phone}."
            )
            
            if meta_token and meta_phone_id and phone_number:
                url = f"https://graph.facebook.com/v19.0/{meta_phone_id}/messages"
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone_number.replace("+", ""),
                    "type": "text",
                    "text": {
                        "preview_url": False,
                        "body": whatsapp_body
                    }
                }
                data = json.dumps(payload).encode('utf-8')
                
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Authorization', f"Bearer {meta_token}")
                req.add_header('Content-Type', 'application/json')
                
                urllib.request.urlopen(req)
                print("WhatsApp welcome message sent.")
        except Exception as e:
            print(f"Failed to send WhatsApp welcome message: {str(e)}")

        # --- Send Email Welcome via Amazon SES ---
        try:
            import boto3
            ses = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'eu-west-1'))
            sender_email = os.environ.get('SENDER_EMAIL', 'no-reply@kapuletu.co.ke')
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; margin: 0; padding: 0; background-color: #f1f5f9; }}
                    .wrapper {{ padding: 40px 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 48px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); }}
                    .header {{ border-bottom: 2px solid #f1f5f9; padding-bottom: 24px; margin-bottom: 32px; text-align: center; }}
                    .header h1 {{ margin: 0; color: #0f172a; font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
                    .header p {{ margin: 8px 0 0; color: #64748b; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }}
                    .content h2 {{ font-size: 22px; color: #0f172a; margin-top: 0; font-weight: 600; }}
                    .content p {{ font-size: 16px; color: #334155; margin-bottom: 24px; }}
                    .value-prop {{ background: linear-gradient(145deg, #f8fafc, #f1f5f9); padding: 28px; border-radius: 8px; margin: 32px 0; border: 1px solid #e2e8f0; }}
                    .value-prop h3 {{ margin: 0 0 16px; color: #0f172a; font-size: 16px; font-weight: 600; }}
                    .feature-list {{ padding-left: 0; list-style: none; margin: 0; }}
                    .feature-list li {{ margin-bottom: 12px; font-size: 15px; color: #475569; position: relative; padding-left: 24px; }}
                    .feature-list li:before {{ content: "✓"; position: absolute; left: 0; color: #2563eb; font-weight: bold; }}
                    .button-container {{ text-align: center; margin: 40px 0; }}
                    .button {{ background-color: #2563eb; color: #ffffff !important; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px; display: inline-block; transition: background-color 0.2s; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2); }}
                    .button:hover {{ background-color: #1d4ed8; }}
                    .footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #94a3b8; text-align: center; }}
                    .footer strong {{ color: #64748b; }}
                    .legal {{ margin-top: 16px; font-size: 11px; color: #cbd5e1; }}
                </style>
            </head>
            <body>
                <div class="wrapper">
                    <div class="container">
                        <div class="header">
                            <h1>KapuLetu</h1>
                            <p>Community Financial Management</p>
                        </div>
                        <div class="content">
                            <h2>Welcome to KapuLetu, {first_name}.</h2>
                            <p>We are writing to formally confirm that your account has been successfully verified and activated. You now have full access to our comprehensive suite of treasury management tools.</p>
                            
                            <div class="value-prop">
                                <h3>Your Financial Infrastructure is Ready</h3>
                                <ul class="feature-list">
                                    <li><strong>Transparent Tracking:</strong> Automatically log and audit every community contribution.</li>
                                    <li><strong>Institutional Reporting:</strong> Generate clear, professional financial statements on demand.</li>
                                    <li><strong>Secure Governance:</strong> Maintain complete administrative oversight with robust security protocols.</li>
                                </ul>
                            </div>
                            
                            <p>To begin structuring your organization's finances, please log in to your secure administrative dashboard and invite your executive team.</p>
                            
                            <div class="button-container">
                                <a href="{dashboard_url}" class="button">Access Secure Dashboard</a>
                            </div>
                            
                            <p>Thank you for choosing KapuLetu. We are committed to providing you with an enterprise-grade platform to manage your community's wealth with absolute transparency and integrity.</p>
                        </div>
                        <div class="footer">
                            <p>If you require administrative assistance or technical support, please reach out to our dedicated operations team at <strong>{support_email}</strong>.</p>
                            <p>&copy; 2026 KapuLetu Systems. All rights reserved.</p>
                            <p class="legal">This email contains secure, transactional information relating to your KapuLetu account. Please do not reply directly to this automated message.</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            ses.send_email(
                Source=sender_email,
                Destination={'ToAddresses': [email]},
                Message={
                    'Subject': {'Data': 'Welcome to KapuLetu! Your account is ready.'},
                    'Body': {'Html': {'Data': html_body}}
                }
            )
            print("Email welcome message sent.")
        except Exception as e:
            print(f"Failed to send Email welcome message: {str(e)}")
            
    except Exception as e:
        import traceback
        print(f"Failed to sync user {email} to database: {str(e)}")
        print(traceback.format_exc())
        # NEVER raise an exception here, otherwise Cognito fails the entire verification process with "Unrecognizable lambda output"
    finally:
        db.close()

    # 4. Return the event to Cognito so it can finalize the signup process
    return event
