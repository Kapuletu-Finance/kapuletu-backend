import os
import logging
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from pydantic import EmailStr
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class CognitoService:
    def __init__(self):
        self.region = os.environ.get('AWS_REGION', 'eu-west-1')
        self.client_id = os.environ.get('COGNITO_CLIENT_ID')
        self.client = boto3.client('cognito-idp', region_name=self.region)

    def _handle_client_error(self, e: ClientError):
        """Translates AWS Cognito errors into clean FastAPI HTTP Exceptions."""
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        logger.warning(f"Cognito Error: {error_code} - {error_message}")
        
        if error_code in ['NotAuthorizedException', 'UserNotFoundException']:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
        elif error_code == 'UsernameExistsException':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
        elif error_code == 'CodeMismatchException':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")
        elif error_code == 'ExpiredCodeException':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired. Please request a new one.")
        elif error_code == 'InvalidPasswordException':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        elif error_code == 'LimitExceededException':
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Please try again later.")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

    def register(self, email: EmailStr, password: str, first_name: str, last_name: str, phone_number: str) -> str:
        """Registers a new user and returns their Cognito User Sub (UUID)."""
        if not self.client_id:
            raise HTTPException(status_code=500, detail="COGNITO_CLIENT_ID environment variable not set")
            
        try:
            response = self.client.sign_up(
                ClientId=self.client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'given_name', 'Value': first_name},
                    {'Name': 'family_name', 'Value': last_name},
                    {'Name': 'phone_number', 'Value': phone_number}
                ]
            )
            return response.get('UserSub')
        except ClientError as e:
            self._handle_client_error(e)

    def verify_account(self, email: EmailStr, code: str):
        try:
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                Username=email,
                ConfirmationCode=code
            )
        except ClientError as e:
            self._handle_client_error(e)

    def login(self, email: EmailStr, password: str) -> Dict[str, Any]:
        """Returns the AuthenticationResult containing tokens."""
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password
                }
            )
            return response.get('AuthenticationResult', {})
        except ClientError as e:
            self._handle_client_error(e)

    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )
            return response.get('AuthenticationResult', {})
        except ClientError as e:
            self._handle_client_error(e)

    def logout(self, access_token: str):
        try:
            self.client.global_sign_out(AccessToken=access_token)
        except ClientError as e:
            self._handle_client_error(e)

    def forgot_password(self, email: EmailStr):
        try:
            self.client.forgot_password(
                ClientId=self.client_id,
                Username=email
            )
        except ClientError as e:
            self._handle_client_error(e)

    def reset_password(self, email: EmailStr, code: str, new_password: str):
        try:
            self.client.confirm_forgot_password(
                ClientId=self.client_id,
                Username=email,
                ConfirmationCode=code,
                Password=new_password
            )
        except ClientError as e:
            self._handle_client_error(e)

    def change_password(self, access_token: str, old_password: str, new_password: str):
        try:
            self.client.change_password(
                PreviousPassword=old_password,
                ProposedPassword=new_password,
                AccessToken=access_token
            )
        except ClientError as e:
            self._handle_client_error(e)

    def get_user(self, access_token: str) -> Dict[str, Any]:
        """Fetches the user details securely using the access token."""
        try:
            response = self.client.get_user(AccessToken=access_token)
            attrs = {attr['Name']: attr['Value'] for attr in response.get('UserAttributes', [])}
            attrs['username'] = response.get('Username')
            return attrs
        except ClientError as e:
            self._handle_client_error(e)

    def request_email_verification(self, access_token: str):
        """Requests Cognito to send a verification code to the user's email."""
        try:
            self.client.get_user_attribute_verification_code(
                AccessToken=access_token,
                AttributeName='email'
            )
        except ClientError as e:
            self._handle_client_error(e)

    def request_phone_verification(self, access_token: str):
        """Requests Cognito to send a verification code to the user's phone number."""
        try:
            self.client.get_user_attribute_verification_code(
                AccessToken=access_token,
                AttributeName='phone_number'
            )
        except ClientError as e:
            self._handle_client_error(e)

    def confirm_phone_verification(self, access_token: str, code: str):
        """Confirms the phone verification code."""
        try:
            self.client.verify_user_attribute(
                AccessToken=access_token,
                AttributeName='phone_number',
                Code=code
            )
        except ClientError as e:
            self._handle_client_error(e)

    def resend_confirmation_code(self, email: EmailStr) -> Dict[str, Any]:
        """Resends the initial registration verification code."""
        try:
            response = self.client.resend_confirmation_code(
                ClientId=self.client_id,
                Username=email
            )
            return response.get('CodeDeliveryDetails', {})
        except ClientError as e:
            self._handle_client_error(e)

    def confirm_email_verification(self, access_token: str, code: str):
        """Verifies the email attribute with the provided code."""
        try:
            self.client.verify_user_attribute(
                AccessToken=access_token,
                AttributeName='email',
                Code=code
            )
        except ClientError as e:
            self._handle_client_error(e)

    def update_profile(self, access_token: str, updates: List[Dict[str, str]]):
        """Updates user attributes in Cognito."""
        try:
            self.client.update_user_attributes(
                UserAttributes=updates,
                AccessToken=access_token
            )
        except ClientError as e:
            self._handle_client_error(e)

cognito_service = CognitoService()
