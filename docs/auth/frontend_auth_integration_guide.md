# Kapuletu Frontend Authentication Integration Guide

This guide outlines the authentication flow, required endpoints, and suggested frontend architecture for seamless integration with the Kapuletu Backend. The backend uses AWS Cognito for authentication, providing secure JWT-based access, and intelligently routes messages based on the specific contact method provided by the user.

---

## 1. Core Concepts

### Dynamic Identifiers (Email vs. Phone Number)
Our endpoints are designed to be dynamic and specifically route verification codes to the provided contact method. For Login, Verification, and Password Recovery, you can provide **either** an `email` or a `phone_number`. 

If you send a `phone_number`, the backend ensures the code is routed via SMS/WhatsApp. If you send an `email`, the code is routed via email.

### Tokens
When a user logs in, the backend returns three JWT tokens:
- **`access_token`**: Used to authorize API requests. Include this in the `Authorization` header.
- **`id_token`**: Contains user identity information.
- **`refresh_token`**: Used to obtain a new `access_token` when it expires (typically after 1 hour). This is a long-lived token.

### API Requests (The Authorization Header)
For all **protected** endpoints, attach the `access_token` to the HTTP headers:
```http
Authorization: Bearer <your_access_token>
```

---

## 2. Authentication Flows

### A. The Signup Flow

1. **Register**: User fills out the signup form.
   - **Endpoint**: `POST /auth/register`
   - **Payload Requirements**: Both `email` and `phone_number` are required here, along with `password`, `first_name`, `last_name`.
   - **Action**: The backend creates the user in Cognito. Based on your flow, AWS Cognito will immediately send a 6-digit verification code to the user's **Phone Number** (via WhatsApp or SMS) to confirm their account. Transition the user to a verification screen.

2. **Verify Account (Phone Number)**: User enters the 6-digit code they received on their phone.
   - **Endpoint**: `POST /auth/verify`
   - **Payload**: 
     ```json
     {
       "phone_number": "+254115749711", 
       "code": "123456"
     }
     ```
   - **Action**: On success, the account is confirmed and the phone number is marked as verified. The user can now log in!
   - *Note*: If they didn't get the code, use `POST /auth/resend-code` with `{"phone_number": "+254115749711"}`.

3. **Verify Email (Later, inside the App)**: 
   Once the user is logged in, you can prompt them to verify their email address.
   - Request Code: `POST /auth/verify-email/request` (Sends code to email)
   - Confirm Code: `POST /auth/verify-email/confirm` with `{"code": "123456"}`

### B. The Login Flow

1. **Login**: User enters credentials.
   - **Endpoint**: `POST /auth/login`
   - **Payload**: Either `email` or `phone_number` along with `password`.
     ```json
     {
       "phone_number": "+254115749711",
       "password": "SecurePassword123!"
     }
     ```
   - **Response**: `{ access_token, refresh_token, id_token, expires_in }`
   - **Action**: Store tokens securely. Update your global auth state to `isAuthenticated = true`.
   
2. **Fetch Profile**: Immediately after login, fetch the user's profile to populate the UI.
   - **Endpoint**: `GET /auth/me` (Protected)
   - **Response**: User details (`first_name`, `email_verified`, `phone_number_verified`, etc.)

### C. The Token Refresh Flow (Background)

The `access_token` expires. You must refresh it seamlessly without logging the user out.

1. **Refresh**: When an API request fails with `401 Unauthorized`.
   - **Endpoint**: `POST /auth/refresh`
   - **Payload**: `{"refresh_token": "..."}`
   - **Response**: `{ access_token, id_token, expires_in }`
   - **Action**: Save the new `access_token` and retry the failed API request.

### D. Password Recovery Flow

1. **Forgot Password**: User forgets password and requests a reset.
   - **Endpoint**: `POST /auth/forgot-password`
   - **Payload**: Send either `"email"` or `"phone_number"`. The code will be routed specifically to that contact.
   - **Action**: Send code. Transition to the Reset Password screen.
   
2. **Reset Password**: User enters the code from their email/SMS and a new password.
   - **Endpoint**: `POST /auth/reset-password`
   - **Payload**: 
     ```json
     {
       "phone_number": "+254115749711",
       "code": "123456",
       "new_password": "NewSecurePassword456!"
     }
     ```
   - **Action**: On success, transition to Login screen.

---

## 3. Profile and Settings Management

These are all **Protected** endpoints (require the `Authorization` header).

- **Get Profile**: `GET /auth/me`
- **Update Profile**: `PATCH /auth/me` (Accepts optional `first_name`, `last_name`, `phone_number`)
- **Change Password**: `POST /auth/change-password` (Requires `old_password` and `new_password`)
- **Get Settings**: `GET /auth/settings`
- **Update Settings**: `POST /auth/settings` (Requires `allow_ai_training` boolean)
- **Logout**: `POST /auth/logout`. Clears the token on the backend. Frontend must clear local tokens and redirect to `/login`.

---

## 4. Suggested Frontend Organization

To ensure a seamless experience, organize your auth logic using an **API Interceptor** and a **Global State Manager** (like React Context, Zustand, or Redux).

### A. API Client (Axios Interceptors)

Create a centralized Axios instance (`api.js` or `api.ts`). Use interceptors to automatically attach the token and handle token refreshes.

```javascript
import axios from 'axios';

const api = axios.create({ baseURL: 'https://api.yourdomain.com' });

// 1. Request Interceptor: Attach Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = \`Bearer \${token}\`;
  }
  return config;
});

// 2. Response Interceptor: Handle Refresh Seamlessly
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // If 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = localStorage.getItem('refresh_token');
        const res = await axios.post('/auth/refresh', { refresh_token: refreshToken });
        
        // Save new token
        localStorage.setItem('access_token', res.data.access_token);
        
        // Retry original request
        originalRequest.headers.Authorization = \`Bearer \${res.data.access_token}\`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        localStorage.clear();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

### B. Global Auth State (Example: Zustand)

Store the authentication state globally so all components know if the user is logged in.

```javascript
// AuthStore pseudo-code
const useAuthStore = create((set) => ({
  user: null,
  isAuthenticated: false,
  
  // Notice we take an 'identifier' object so we can pass { phone_number } or { email }
  login: async (credentials) => {
    // credentials might be: { phone_number: "+254115749711", password: "..." }
    const tokens = await api.post('/auth/login', credentials);
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    
    const userProfile = await api.get('/auth/me');
    set({ user: userProfile, isAuthenticated: true });
  },
  
  logout: async () => {
    await api.post('/auth/logout');
    localStorage.clear();
    set({ user: null, isAuthenticated: false });
  }
}));
```

### C. UI Best Practices for Dynamic Inputs
When building your login or verification forms, use a single input field labeled "Email or Phone Number" or provide explicit tabs/buttons to switch between Email and Phone inputs. Based on what the user types (e.g., regex check for `@` vs `+`), your frontend logic should dynamically construct the JSON payload:
- Contains `@` ➡️ `{"email": value}`
- Contains numbers/`+` ➡️ `{"phone_number": value}`
