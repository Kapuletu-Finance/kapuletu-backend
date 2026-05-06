import json
import os
import boto3
from botocore.exceptions import ClientError

cognito = boto3.client('cognito-idp', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID')

def respond(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }

def handler(event, context):
    path = event.get('resource', '')
    if not path:
        path = event.get('path', '')
    http_method = event.get('httpMethod', '')
    
    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        body = {}

    # Extract JWT token for protected routes
    auth_header = event.get('headers', {}).get('Authorization', '')
    access_token = auth_header.replace('Bearer ', '') if auth_header else None

    try:
        # ==========================================
        # PUBLIC ENDPOINTS
        # ==========================================
        if path == '/auth/register' and http_method == 'POST':
            response = cognito.sign_up(
                ClientId=CLIENT_ID,
                Username=body.get('email'),
                Password=body.get('password'),
                UserAttributes=[
                    {'Name': 'email', 'Value': body.get('email')},
                    {'Name': 'given_name', 'Value': body.get('first_name', '')},
                    {'Name': 'family_name', 'Value': body.get('last_name', '')},
                    {'Name': 'phone_number', 'Value': body.get('phone_number', '')}
                ]
            )
            return respond(200, {"message": "User registered. Please verify email/phone.", "sub": response.get('UserSub')})
            
        elif path == '/auth/verify' and http_method == 'POST':
            cognito.confirm_sign_up(
                ClientId=CLIENT_ID,
                Username=body.get('email'),
                ConfirmationCode=body.get('code')
            )
            return respond(200, {"message": "Verification successful."})

        elif path == '/auth/login' and http_method == 'POST':
            response = cognito.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': body.get('email'),
                    'PASSWORD': body.get('password')
                }
            )
            return respond(200, response.get('AuthenticationResult'))

        elif path == '/auth/refresh' and http_method == 'POST':
            response = cognito.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': body.get('refresh_token')
                }
            )
            return respond(200, response.get('AuthenticationResult'))

        elif path == '/auth/forgot-password' and http_method == 'POST':
            cognito.forgot_password(
                ClientId=CLIENT_ID,
                Username=body.get('email')
            )
            return respond(200, {"message": "Password reset code sent."})

        elif path == '/auth/reset-password' and http_method == 'POST':
            cognito.confirm_forgot_password(
                ClientId=CLIENT_ID,
                Username=body.get('email'),
                ConfirmationCode=body.get('code'),
                Password=body.get('new_password')
            )
            return respond(200, {"message": "Password reset successful."})

        # ==========================================
        # PROTECTED ENDPOINTS (Requires Bearer Token)
        # ==========================================
        elif path == '/auth/logout' and http_method == 'POST':
            if not access_token: return respond(401, {"error": "Missing token"})
            cognito.global_sign_out(AccessToken=access_token)
            return respond(200, {"message": "Logged out successfully."})

        elif path == '/auth/change-password' and http_method == 'POST':
            if not access_token: return respond(401, {"error": "Missing token"})
            cognito.change_password(
                PreviousPassword=body.get('old_password'),
                ProposedPassword=body.get('new_password'),
                AccessToken=access_token
            )
            return respond(200, {"message": "Password changed successfully."})

        elif path == '/auth/me' and http_method == 'GET':
            if not access_token: return respond(401, {"error": "Missing token"})
            response = cognito.get_user(AccessToken=access_token)
            user_data = {attr['Name']: attr['Value'] for attr in response.get('UserAttributes', [])}
            user_data['username'] = response.get('Username')
            return respond(200, {"user": user_data})

        elif path == '/auth/me' and http_method == 'PATCH':
            if not access_token: return respond(401, {"error": "Missing token"})
            
            # Map backend keys to Cognito schema
            updates = []
            if 'first_name' in body: updates.append({'Name': 'given_name', 'Value': body['first_name']})
            if 'last_name' in body: updates.append({'Name': 'family_name', 'Value': body['last_name']})
            if 'phone_number' in body: updates.append({'Name': 'phone_number', 'Value': body['phone_number']})
            
            if updates:
                cognito.update_user_attributes(
                    UserAttributes=updates,
                    AccessToken=access_token
                )
            return respond(200, {"message": "Profile updated successfully."})

        else:
            return respond(404, {"error": "Endpoint not found"})

    except ClientError as e:
        error_msg = e.response['Error']['Message']
        return respond(400, {"error": error_msg})
    except Exception as e:
        return respond(500, {"error": str(e)})
