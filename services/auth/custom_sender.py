import os
import json
import base64
import urllib.request
import urllib.parse
# import aws_encryption_sdk # Required in production to decrypt Cognito's code
# from aws_encryption_sdk import StrictAwsKmsMasterKeyProvider

def handler(event, context):
    """
    AWS Cognito Custom SMS Sender Trigger.
    
    Why this exists: 
    Cognito natively only sends standard SMS text messages for phone verification.
    Since KapuLetu requires WhatsApp, we use this trigger to intercept Cognito's 
    verification code BEFORE it sends an SMS, and we manually route it through 
    the Twilio WhatsApp API instead.
    """
    
    # Only intercept if this is a Sign Up verification or Forgot Password
    if event.get('triggerSource') in ['CustomSMSSender_SignUp', 'CustomSMSSender_ForgotPassword']:
        
        phone_number = event['request']['userAttributes'].get('phone_number')
        encrypted_code = event['request']['code']
        
        print(f"Intercepted Cognito SMS. Preparing to send WhatsApp to {phone_number}")
        
        # 1. Decrypt the code 
        # (Cognito encrypts the code for security. You will need to provision a KMS 
        # key in kapuletu-infra and use aws_encryption_sdk to decrypt it here).
        # 
        # kms_key_arn = os.environ['KMS_KEY_ID']
        # master_key_provider = StrictAwsKmsMasterKeyProvider(key_ids=[kms_key_arn])
        # decrypted_code, _ = aws_encryption_sdk.decrypt(source=base64.b64decode(encrypted_code), key_provider=master_key_provider)
        # plain_text_code = decrypted_code.decode('utf-8')
        
        plain_text_code = "<DECRYPTED_CODE>" # Placeholder
        
        # 2. Send the message via Twilio WhatsApp API
        twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID', 'YOUR_SID')
        twilio_token = os.environ.get('TWILIO_AUTH_TOKEN', 'YOUR_TOKEN')
        twilio_whatsapp_number = os.environ.get('TWILIO_WHATSAPP_NUMBER', '+14155238886')
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
        
        data = urllib.parse.urlencode({
            'From': f"whatsapp:{twilio_whatsapp_number}",
            'To': f"whatsapp:{phone_number}",
            'Body': f"Welcome to KapuLetu! Your verification code is: {plain_text_code}"
        }).encode('utf-8')
        
        # Create HTTP Request to Twilio
        # req = urllib.request.Request(url, data=data, method='POST')
        # req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{twilio_sid}:{twilio_token}".encode()).decode())
        # 
        # try:
        #     urllib.request.urlopen(req)
        #     print("WhatsApp verification code sent successfully.")
        # except Exception as e:
        #     print(f"Failed to send WhatsApp message: {str(e)}")
        
    return event
