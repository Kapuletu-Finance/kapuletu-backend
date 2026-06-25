import os
import json
import logging
import base64
import urllib.parse
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    AWS Cognito Custom Message Trigger.
    Returns professional HTML email templates and sends WhatsApp verification codes.
    """
    trigger = event.get('triggerSource')
    user_attrs = event['request'].get('userAttributes', {})
    phone_number = user_attrs.get('phone_number')
    first_name = user_attrs.get('given_name', 'there')
    code = event['request'].get('codeParameter')
    
    # 1. Professional WhatsApp Logic (Twilio)
    if trigger in ['CustomMessage_SignUp', 'CustomMessage_ForgotPassword']:
        twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_number = os.environ.get('TWILIO_WHATSAPP_NUMBER')
        
        if twilio_sid and twilio_token and phone_number:
            logger.info(f"Attempting WhatsApp send to {phone_number} using SID {twilio_sid[:5]}...")
            whatsapp_body = (
                f" *KapuLetu Security*\n\n"
                f"Hello {first_name}! Your one-time verification code is: *{code}*\n\n"
                f"Please enter this in the app to continue. If you didn't request this, "
                f"please ignore this message."
            )
            
            try:
                url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
                data = urllib.parse.urlencode({
                    'From': f"whatsapp:{twilio_number}",
                    'To': f"whatsapp:{phone_number}",
                    'Body': whatsapp_body
                }).encode('utf-8')
                
                req = urllib.request.Request(url, data=data, method='POST')
                auth_str = base64.b64encode(f"{twilio_sid}:{twilio_token}".encode()).decode()
                req.add_header('Authorization', f"Basic {auth_str}")
                urllib.request.urlopen(req)
                logger.info(f"SUCCESS: WhatsApp code sent to {phone_number}")
            except Exception as e:
                logger.error(f"ERROR: WhatsApp delivery failed: {str(e)}")
        else:
            logger.warning(f"SKIPPING WhatsApp: Missing Twilio Credentials (SID: {bool(twilio_sid)}, Token: {bool(twilio_token)})")

    # 2. Designer HTML Email Template & Native SMS Fallback
    if trigger in ['CustomMessage_SignUp', 'CustomMessage_ResendCode']:
        event['response']['emailSubject'] = "Welcome to KapuLetu - Verify Your Account"
        event['response']['emailMessage'] = get_html_template(first_name, code, "verify your account")
        event['response']['smsMessage'] = f"KapuLetu: Your verification code is {code}. It expires in 24 hours."
    
    elif trigger == 'CustomMessage_ForgotPassword':
        event['response']['emailSubject'] = "Reset Your KapuLetu Password"
        event['response']['emailMessage'] = get_html_template(first_name, code, "reset your password")
        event['response']['smsMessage'] = f"KapuLetu: Your password reset code is {code}."
        
    elif trigger == 'CustomMessage_VerifyUserAttribute':
        event['response']['emailSubject'] = "Verify Your KapuLetu Contact Details"
        event['response']['emailMessage'] = get_html_template(first_name, code, "verify your email address")
        event['response']['smsMessage'] = f"KapuLetu: Your verification code is {code}."

    return event

def get_html_template(name, code, action_text):
    """Returns a premium HTML email template."""
    return f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #f4f7f9; padding: 40px; margin: 0;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #0a2540; margin: 0; font-size: 28px; letter-spacing: -0.5px;">KapuLetu</h1>
            </div>
            <div style="color: #425466; font-size: 16px; line-height: 24px;">
                <p>Hello {name},</p>
                <p>To {action_text}, please use the following secure verification code:</p>
                
                <div style="background-color: #f8fafd; border: 1px dashed #cbd5e0; border-radius: 8px; padding: 20px; text-align: center; margin: 30px 0;">
                    <span style="font-family: 'Courier New', monospace; font-size: 32px; font-weight: bold; color: #0056b3; letter-spacing: 5px;">{code}</span>
                </div>
                
                <p style="font-size: 14px; color: #718096;">This code will expire in 24 hours. If you did not request this, you can safely ignore this email.</p>
            </div>
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #edf2f7; font-size: 12px; color: #a0aec0; text-align: center;">
                <p>&copy; 2026 KapuLetu Treasury Systems. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
