# Frontend 2FA Login Implementation Guide

## Overview
This document explains how to implement the login flow in the frontend, supporting both regular login and Two-Factor Authentication (2FA).

---

## API Endpoint
**POST** `/api/auth/login/`

**Base URL:** `http://127.0.0.1:8000/api`

---

## Login Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  User enters email + password                                │
│  Clicks "Login" button                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  POST /api/auth/login/                                       │
│  {                                                           │
│    "email": "user@example.com",                              │
│    "password": "password123"                                 │
│  }                                                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend checks: user.two_factor_enabled?                    │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
    [FALSE]                  [TRUE]
         │                       │
         │                       ▼
         │          ┌──────────────────────────────────┐
         │          │ Check: two_factor_code provided? │
         │          └─────────┬────────────────────────┘
         │                    │
         │              ┌─────┴─────┐
         │              │           │
         │              ▼           ▼
         │           [NO]        [YES]
         │              │           │
         │              ▼           ▼
         │    ┌───────────────┐  ┌──────────────────┐
         │    │ Return ERROR  │  │ Verify TOTP code │
         │    │ requires_2fa  │  └────────┬─────────┘
         │    │ = true        │           │
         │    └───────────────┘      ┌────┴─────┐
         │                           │          │
         │                           ▼          ▼
         │                       [VALID]    [INVALID]
         │                           │          │
         ▼                           │          ▼
┌─────────────────┐                 │    ┌──────────────┐
│ Return SUCCESS  │◄────────────────┘    │ Return ERROR │
│ + JWT tokens    │                      │ Invalid code │
└─────────────────┘                      └──────────────┘
```

---

## Scenario 1: Login WITHOUT 2FA (Normal Login)

### Request
```http
POST /api/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "user": {
      "id": 1,
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "is_admin": false,
      "is_employer": true,
      "is_employee": false,
      "profile_completed": true,
      "two_factor_enabled": false,
      "created_at": "2025-01-15T10:30:00Z"
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    },
    "profile_incomplete": false
  },
  "errors": []
}
```

### Frontend Action
1. Store `access` token in memory/state
2. Store `refresh` token in localStorage/secure storage
3. Check if `profile_incomplete` is true → redirect to profile completion
4. Otherwise → redirect to dashboard

---

## Scenario 2: Login WITH 2FA Enabled

### Step 1: Initial Login Attempt (Without 2FA Code)

#### Request
```http
POST /api/auth/login/
Content-Type: application/json

{
  "email": "employer@company.com",
  "password": "password123"
}
```

#### Error Response (400 Bad Request)
```json
{
  "success": false,
  "message": "Login failed.",
  "data": {},
  "errors": {
    "two_factor_code": "2FA is enabled. Please provide authentication code.",
    "requires_2fa": true
  }
}
```

#### Frontend Action
1. **Detect:** Check if `errors.requires_2fa === true`
2. **Show:** Display 2FA code input field
3. **Keep:** Store email and password in state (for next request)
4. **Focus:** Auto-focus on 2FA input field
5. **Message:** "Enter the 6-digit code from your authenticator app"

---

### Step 2: Login with 2FA Code

#### Request
```http
POST /api/auth/login/
Content-Type: application/json

{
  "email": "employer@company.com",
  "password": "password123",
  "two_factor_code": "123456"
}
```

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "user": {
      "id": 2,
      "email": "employer@company.com",
      "first_name": "Jane",
      "last_name": "Smith",
      "is_admin": false,
      "is_employer": true,
      "is_employee": false,
      "profile_completed": true,
      "two_factor_enabled": true,
      "created_at": "2025-01-10T08:00:00Z"
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    },
    "profile_incomplete": false
  },
  "errors": []
}
```

#### Frontend Action
Same as normal login:
1. Store tokens
2. Redirect to appropriate page

---

#### Invalid 2FA Code Response (400 Bad Request)
```json
{
  "success": false,
  "message": "Login failed.",
  "data": {},
  "errors": {
    "two_factor_code": "Invalid authentication code."
  }
}
```

#### Frontend Action
1. Show error message under 2FA input
2. Clear 2FA input field
3. Allow user to try again
4. **Note:** Codes expire every 30 seconds, user should try current code

---

## Common Error Responses

### 1. Invalid Credentials
```json
{
  "success": false,
  "message": "Login failed.",
  "data": {},
  "errors": {
    "email": "Invalid email or password."
  }
}
```

### 2. Account Not Activated
```json
{
  "success": false,
  "message": "Login failed.",
  "data": {},
  "errors": {
    "email": "Account is not activated. Please check your email for activation instructions."
  }
}
```

### 3. Rate Limiting (10 attempts per hour)
```json
{
  "success": false,
  "message": "Too many login attempts. Please try again later.",
  "data": {},
  "errors": []
}
```

---

## Frontend Implementation Pseudocode

```javascript
// Login Form Component
const LoginForm = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [requires2FA, setRequires2FA] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const payload = {
        email,
        password,
      };

      // Add 2FA code if we're in 2FA mode
      if (requires2FA) {
        payload.two_factor_code = twoFactorCode;
      }

      const response = await fetch('http://127.0.0.1:8000/api/auth/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.success) {
        // Login successful
        localStorage.setItem('refresh_token', data.data.tokens.refresh);
        localStorage.setItem('access_token', data.data.tokens.access);
        
        // Check profile status
        if (data.data.profile_incomplete) {
          navigate('/complete-profile');
        } else {
          navigate('/dashboard');
        }
      } else {
        // Check if 2FA is required
        if (data.errors.requires_2fa === true) {
          setRequires2FA(true);
          setError('Please enter your 6-digit authentication code');
        } else if (data.errors.two_factor_code) {
          setError(data.errors.two_factor_code);
          setTwoFactorCode(''); // Clear invalid code
        } else if (data.errors.email) {
          setError(data.errors.email);
        } else {
          setError(data.message || 'Login failed');
        }
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleLogin}>
      {error && <div className="error">{error}</div>}
      
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        required
        disabled={requires2FA} // Disable when in 2FA mode
      />
      
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        required
        disabled={requires2FA} // Disable when in 2FA mode
      />
      
      {/* Only show when 2FA is required */}
      {requires2FA && (
        <div>
          <input
            type="text"
            value={twoFactorCode}
            onChange={(e) => setTwoFactorCode(e.target.value)}
            placeholder="6-digit code"
            maxLength={6}
            pattern="[0-9]{6}"
            required
            autoFocus
          />
          <button 
            type="button" 
            onClick={() => {
              setRequires2FA(false);
              setTwoFactorCode('');
              setError('');
            }}
          >
            Back
          </button>
        </div>
      )}
      
      <button type="submit" disabled={loading}>
        {loading ? 'Logging in...' : requires2FA ? 'Verify & Login' : 'Login'}
      </button>
    </form>
  );
};
```

---

## Important Notes

### 1. 2FA Codes (TOTP)
- **Source:** Authenticator apps (Google Authenticator, Authy, Microsoft Authenticator)
- **Format:** 6-digit numeric code
- **Expiration:** Every 30 seconds
- **Validation Window:** Backend accepts codes within ±30 seconds (for clock drift)
- **No SMS/Email:** This is app-based 2FA only

### 2. Security Best Practices
- Never store passwords in state longer than necessary
- Clear 2FA code after failed attempt
- Implement rate limiting UI feedback
- Use HTTPS in production
- Store refresh token securely (httpOnly cookies recommended)
- Use access token for API requests: `Authorization: Bearer {access_token}`

### 3. User Experience
- Auto-submit when 6 digits are entered (optional enhancement)
- Show countdown timer for code expiration (optional)
- Provide "Back" button in 2FA mode
- Clear error messages
- Show loading states during requests
- Don't clear email/password on 2FA requirement (better UX)

### 4. Token Management
- **Access Token:** Short-lived (typically 15-60 minutes), use for API requests
- **Refresh Token:** Long-lived (typically 7-30 days), use to get new access token
- When access token expires, use refresh token at `/api/auth/token/refresh/`

---

## Testing Checklist

- [ ] Test normal login (2FA disabled)
- [ ] Test login with 2FA enabled (correct code)
- [ ] Test login with 2FA enabled (wrong code)
- [ ] Test login with 2FA enabled (expired code)
- [ ] Test invalid credentials
- [ ] Test inactive account
- [ ] Test rate limiting (10 attempts)
- [ ] Test network errors
- [ ] Test profile incomplete redirect
- [ ] Test token storage and retrieval
- [ ] Test "Back" button in 2FA mode
- [ ] Test UI loading states
- [ ] Test error message display

---

## Example API Calls with curl

### Normal Login
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'
```

### Login with 2FA
```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "employer@company.com",
    "password": "password123",
    "two_factor_code": "123456"
  }'
```

---

## Questions?

If you have questions about the implementation, please refer to:
- `accounts/views.py` - LoginView implementation
- `accounts/serializers.py` - LoginSerializer validation logic
- `accounts/utils.py` - TOTP verification functions
- `HR_API_Insomnia_Collection.json` - Complete API examples

**Key Point:** The 2FA verification happens automatically inside the `/auth/login/` endpoint. You never need to call `/auth/2fa/verify/` during login - that endpoint is only used once when initially setting up 2FA.
