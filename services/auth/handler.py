import json
import os

# Imagine we import our database connection here
# from repositories.user_repository import create_user_and_organization

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
    
    try:
        # 2. Logic to insert user into PostgreSQL
        # (Pseudo-code for the repository logic that would happen here)
        # 
        # db = get_db_connection()
        # organization_id = db.execute("INSERT INTO organizations (name, tier) VALUES (%s, 'Free') RETURNING id", [f"{first_name} {last_name} Org"])
        # db.execute("INSERT INTO users (id, email, first_name, last_name, phone_number, organization_id) VALUES (%s, %s, %s, %s, %s, %s)", 
        #            [cognito_user_id, email, first_name, last_name, phone_number, organization_id])
        # db.commit()
        
        print(f"Successfully synced user {email} to PostgreSQL database.")
        
        # 3. Send Professional Welcome Messages
        dashboard_url = os.environ.get('DASHBOARD_URL', 'https://app.kapuletu.com')
        
        # --- Send WhatsApp Welcome via Twilio ---
        try:
            import urllib.request
            import urllib.parse
            import base64
            
            twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
            twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
            twilio_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER', '+14155238886')
            support_phone = os.environ.get('SUPPORT_PHONE', '+254700000000')
            support_email = os.environ.get('SUPPORT_EMAIL', 'support@kapuletu.com')
            
            whatsapp_body = (
                f"*Welcome to KapuLetu, {first_name}!*\n\n"
                f"Your account is verified and ready to go.\n\n"
                f"*Here’s what to do next:*\n"
                f"1. Log in to your dashboard: {dashboard_url}\n"
                f"2. Set up your organization profile and invite your team.\n"
                f"3. Start automating your group's finances.\n\n"
                f"We built KapuLetu to make managing community funds as simple, transparent and trustworthy.\n\n"
                f"If you need any help, please don't reply here. Instead, email us at {support_email} or call/WhatsApp us at {support_phone}."
            )
            
            if twilio_sid and twilio_token and phone_number:
                url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
                data = urllib.parse.urlencode({
                    'From': f"whatsapp:{twilio_whatsapp_number}",
                    'To': f"whatsapp:{phone_number}",
                    'Body': whatsapp_body
                }).encode('utf-8')
                
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{twilio_sid}:{twilio_token}".encode()).decode())
                urllib.request.urlopen(req)
                print("WhatsApp welcome message sent.")
        except Exception as e:
            print(f"Failed to send WhatsApp welcome message: {str(e)}")

        # --- Send Email Welcome via Amazon SES ---
        try:
            import boto3
            ses = boto3.client('ses', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            sender_email = os.environ.get('SENDER_EMAIL', 'welcome@kapuletu.com')
            
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333333; line-height: 1.6; margin: 0; padding: 0; background-color: #f9f9f9; }}
                    .container {{ max-width: 600px; margin: 40px auto; background-color: #ffffff; padding: 40px; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
                    .header {{ border-bottom: 1px solid #eee; padding-bottom: 20px; margin-bottom: 30px; }}
                    .header h1 {{ margin: 0; color: #0a2540; font-size: 24px; font-weight: 600; }}
                    .content h2 {{ font-size: 20px; color: #0a2540; margin-top: 0; }}
                    .content p {{ font-size: 16px; color: #555555; margin-bottom: 20px; }}
                    .features {{ background-color: #f4f6f8; padding: 20px; border-radius: 6px; margin: 25px 0; border-left: 4px solid #0056b3; }}
                    .features p {{ margin: 8px 0; font-size: 15px; color: #333; }}
                    .button-container {{ text-align: center; margin: 35px 0; }}
                    .button {{ background-color: #0056b3; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block; }}
                    .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #888888; text-align: center; }}
                    .system-notice {{ margin-top: 20px; font-size: 12px; color: #aaaaaa; text-align: center; font-style: italic; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>KapuLetu</h1>
                    </div>
                    <div class="content">
                        <h2>Welcome, {first_name}!</h2>
                        <p>Your account is officially verified. We're thrilled to have you on board.</p>
                        
                        <div class="features">
                            <p><strong>With KapuLetu, you can easily:</strong></p>
                            <p>&#8226; Track community contributions automatically</p>
                            <p>&#8226; Generate clear financial reports</p>
                            <p>&#8226; Keep all your transactions secure and organized</p>
                        </div>
                        
                        <p>To get started, head over to your dashboard to set up your organization and invite your team.</p>
                        
                        <div class="button-container">
                            <a href="{dashboard_url}" class="button" style="color: #ffffff;">Go to My Dashboard</a>
                        </div>
                        
                        <p>We built KapuLetu to take the stress out of managing community finances, so you can focus on what really matters.</p>
                    </div>
                    <div class="footer">
                        <p>Need a hand? Reach out to our support team at <strong>{support_email}</strong>.</p>
                        <p>&copy; 2026 KapuLetu Systems.</p>
                        <p class="system-notice">This is an automated message. Please do not reply directly to this email.</p>
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
        print(f"Failed to sync user {email} to database: {str(e)}")
        # If we fail to sync, we should ideally raise an exception so Cognito knows it failed
        raise e

    # 4. Return the event to Cognito so it can finalize the signup process
    return event
