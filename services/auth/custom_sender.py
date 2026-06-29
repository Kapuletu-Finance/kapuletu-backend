import os
import json
import logging
import base64
import urllib.parse
import urllib.request
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)
kms_client = boto3.client('kms')

def decrypt_code(encrypted_code):
    try:
        decoded_code = base64.b64decode(encrypted_code)
        response = kms_client.decrypt(CiphertextBlob=decoded_code)
        return response['Plaintext'].decode('utf-8')
    except Exception as e:
        logger.error(f"KMS decryption failed: {str(e)}")
        return None

def send_resend_email(to_email, subject, html_body):
    resend_api_key = os.environ.get('RESEND_API_KEY')
    if not resend_api_key:
        logger.error("Missing RESEND_API_KEY")
        return

    url = "https://api.resend.com/emails"
    payload = {
        "from": "KapuLetu <no-reply@kapuletu.co.ke>",
        "to": [to_email],
        "subject": subject,
        "html": html_body
    }
    data = json.dumps(payload).encode('utf-8')
    
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f"Bearer {resend_api_key}")
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req)
        logger.info(f"SUCCESS: Resend email sent to {to_email}")
    except Exception as e:
        logger.error(f"ERROR: Resend email delivery failed: {str(e)}")

def handler(event, context):
    """
    AWS Cognito Custom Trigger.
    Handles CustomMessage (WhatsApp/SMS) and CustomEmailSender (Resend API).
    """
    trigger = event.get('triggerSource')
    user_attrs = event['request'].get('userAttributes', {})
    phone_number = user_attrs.get('phone_number')
    email = user_attrs.get('email')
    first_name = user_attrs.get('given_name', 'there')
    
    # ---------------------------------------------------------
    # 1. CustomMessage Logic (WhatsApp & Cognito Native SMS)
    # ---------------------------------------------------------
    if trigger.startswith('CustomMessage_'):
        code = event['request'].get('codeParameter')
        
        # WhatsApp Delivery
        if trigger in ['CustomMessage_SignUp', 'CustomMessage_ForgotPassword']:
            meta_token = os.environ.get('META_ACCESS_TOKEN')
            meta_phone_id = os.environ.get('META_PHONE_NUMBER_ID')
            
            if meta_token and meta_phone_id and phone_number:
                logger.info(f"Attempting WhatsApp send to {phone_number}...")
                try:
                    url = f"https://graph.facebook.com/v19.0/{meta_phone_id}/messages"
                    payload = {
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": phone_number.replace("+", ""),
                        "type": "template",
                        "template": {
                            "name": "kapuletu_auth_otp",
                            "language": {"code": "en_US"},
                            "components": [
                                {
                                    "type": "body",
                                    "parameters": [{"type": "text", "text": str(code)}]
                                },
                                {
                                    "type": "button",
                                    "sub_type": "url",
                                    "index": "0",
                                    "parameters": [{"type": "text", "text": str(code)}]
                                }
                            ]
                        }
                    }
                    data = json.dumps(payload).encode('utf-8')
                    req = urllib.request.Request(url, data=data, method='POST')
                    req.add_header('Authorization', f"Bearer {meta_token}")
                    req.add_header('Content-Type', 'application/json')
                    urllib.request.urlopen(req)
                    logger.info(f"SUCCESS: WhatsApp code sent to {phone_number}")
                except Exception as e:
                    logger.error(f"ERROR: WhatsApp delivery failed: {str(e)}")
            else:
                logger.warning("SKIPPING WhatsApp: Missing Meta Credentials")

        # SMS Fallback (Required by Cognito)
        if trigger in ['CustomMessage_SignUp', 'CustomMessage_ResendCode']:
            event['response']['smsMessage'] = f"KapuLetu: Your verification code is {code}. It expires in 10 minutes."
        elif trigger == 'CustomMessage_ForgotPassword':
            event['response']['smsMessage'] = f"KapuLetu: Your password reset code is {code}."
        elif trigger == 'CustomMessage_VerifyUserAttribute':
            event['response']['smsMessage'] = f"KapuLetu: Your verification code is {code}."
            
        # Dummy Email fields (Cognito requires them if CustomMessage is triggered, but CustomEmailSender overrides actual sending)
        event['response']['emailSubject'] = "KapuLetu Verification"
        event['response']['emailMessage'] = "Please check your KapuLetu verification code."
        
        return event

    # ---------------------------------------------------------
    # 2. CustomEmailSender Logic (Resend API)
    # ---------------------------------------------------------
    elif trigger.startswith('CustomEmailSender_'):
        encrypted_code = event['request'].get('code')
        if not encrypted_code:
            logger.error("No encrypted code found in event.")
            return event
            
        code = decrypt_code(encrypted_code)
        if not code:
            return event
            
        subject = "KapuLetu Verification"
        action_text = "verify your account"
        
        if trigger in ['CustomEmailSender_SignUp', 'CustomEmailSender_ResendCode']:
            subject = "Welcome to KapuLetu - Verify Your Account"
            action_text = "verify your account"
        elif trigger == 'CustomEmailSender_ForgotPassword':
            subject = "Reset Your KapuLetu Password"
            action_text = "reset your password"
        elif trigger == 'CustomEmailSender_VerifyUserAttribute':
            subject = "Verify Your KapuLetu Contact Details"
            action_text = "verify your email address"
            
        html_body = get_html_template(first_name, code, action_text)
        
        if email:
            send_resend_email(email, subject, html_body)
            
        return event

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
                
                <p style="font-size: 14px; color: #718096;">This code will expire in 10 minutes. If you did not request this, you can safely ignore this email.</p>
            </div>
            <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #edf2f7; font-size: 12px; color: #a0aec0; text-align: center;">
                <p>&copy; 2026 KapuLetu Treasury Systems. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
