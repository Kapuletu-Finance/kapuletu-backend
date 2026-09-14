How to Test the Auth API Online
Since your API is now deployed and the DNS is fixed, you don't need Postman or any external tools to test this. You can use your built-in interactive developer portal!

Open the API Explorer: Go to your live URL: https://dev-api.kapuletu.co.ke/docs
Register a Test User:
Scroll down to the 2. Authentication section.
Click on POST /auth/register > Try it out.
Fill in the JSON body with a test email, password, name, and phone number, then click Execute. You should get a success response.
Verify the Account:
Check the email address you used; AWS Cognito will have sent a 6-digit verification code.
Go to POST /auth/verify > Try it out.
Enter the email and the 6-digit code, then click Execute. (Behind the scenes, this will also trigger your DB sync and welcome emails!).
Log In (The Magic Step):
Scroll to the very top of the page and click the green Authorize padlock button.
Enter your test email as the username and your password.
Click Authorize. Swagger UI will hit your /auth/token endpoint, grab the JWT access token, and automatically attach it to all future requests you make on the page!
Test a Protected Endpoint:
Scroll to GET /auth/me > Try it out > Execute.
Because you are "Authorized", it will seamlessly pass the token, validate it, and return your full user profile!

## Next Steps

- **Update Profile**: Test the PUT /auth/profile endpoint to update your user information.
- **Logout**: Test the POST /auth/logout endpoint to end your session.
- **Password Reset**: Test the POST /auth/forgot-password and POST /auth/reset-password endpoints to verify the password recovery flow.