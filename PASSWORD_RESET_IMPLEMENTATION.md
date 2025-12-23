# Password Management Features - Implementation Summary

## Overview
Implemented secure password management features including password reset (for unauthenticated users) and password change (for authenticated users).

## Features Implemented

### 1. Request Password Reset (Unauthenticated)
- **Endpoint**: `POST /api/auth/password-reset/request/`
- User enters their email
- System checks if email exists
- Generates random 6-digit code
- Sends code to user's email
- Code stored in cache (NOT database) with 5-minute expiry
- Rate limited: 5 requests per hour per IP

### 2. Verify Code and Reset Password (Unauthenticated)
- **Endpoint**: `POST /api/auth/password-reset/verify/`
- User enters email, 6-digit code, new password, and confirm password
- System verifies code from cache
- Validates passwords match and meet requirements
- Updates user password
- Deletes code from cache
- Rate limited: 5 requests per hour per IP

### 3. Resend Reset Code (Unauthenticated)
- **Endpoint**: `POST /api/auth/password-reset/resend/`
- User can request a new code if previous one expired
- Generates new 6-digit code
- Overwrites old code in cache
- Sends new code via email
- Rate limited: 5 requests per hour per IP

### 4. Change Password (Authenticated)
- **Endpoint**: `POST /api/auth/change-password/`
- Available to all authenticated users (admin, employer, employee)
- Requires current password for verification
- User enters old password, new password, and confirm new password
- Validates current password is correct
- Ensures new password is different from current password
- Validates passwords match and meet requirements
- Updates user password
- Rate limited: 10 requests per hour per user

## Files Created/Modified

### New Files
1. **templates/emails/password_reset_code.html** - HTML email template
2. **templates/emails/password_reset_code.txt** - Plain text email template

### Modified Files
1. **accounts/serializers.py**
   - Added `RequestPasswordResetSerializer`
   - Added `VerifyResetCodeSerializer`
   - Added `ResendResetCodeSerializer`
   - Added `ChangePasswordSerializer`

2. **accounts/utils.py**
   - Added `generate_reset_code()` - Generates 6-digit random code
   - Added `send_password_reset_email()` - Sends email with code
   - Added `store_reset_code()` - Stores code in cache with 5-min expiry
   - Added `verify_reset_code()` - Verifies code from cache
   - Added `delete_reset_code()` - Removes code after successful reset

3. **accounts/views.py**
   - Added `RequestPasswordResetView`
   - Added `VerifyResetCodeView`
   - Added `ResendResetCodeView`
   - Added `ChangePasswordView`

4. **accounts/urls.py**
   - Added URL routes for password reset endpoints
   - Added URL route for change password endpoint

5. **config/settings.py**
   - Added `CACHES` configuration for in-memory cache

6. **INSOMNIA_API_ENDPOINTS.md**
   - Added documentation for password reset endpoints
   - Added documentation for change password endpoint

## Security Features

### Password Reset (Unauthenticated)
1. **No Database Storage**: Codes are stored in cache only, not in database
2. **5-Minute Expiry**: Codes automatically expire after 5 minutes
3. **Rate Limiting**: 5 requests per hour per IP address
4. **Password Validation**: Django's built-in password validators
5. **Email Verification**: Only registered emails can request reset
6. **Code Deletion**: Code deleted immediately after successful reset
7. **Secure Code Generation**: Uses Python's `random.choices` with digits

### Password Change (Authenticated)
### Password Reset Flow (Forgot Password)
1. **User clicks "Forgot Password"**
   ```json
   POST /api/auth/password-reset/request/
   {
     "email": "user@example.com"
   }
   ```

2. **User receives email with 6-digit code** (e.g., "123456")

3. **User enters code and new password**
   ```json
   POST /api/auth/password-reset/verify/
   {
     "email": "user@example.com",
     "code": "123456",
     "password": "NewPassword@123",
     "confirm_password": "NewPassword@123"
   }
   ```

4. **If code expires, user can resend**
   ```json
   POST /api/auth/password-reset/resend/
   {
     "email": "user@example.com"
   }
   ```

### Password Change Flow (Authenticated Users)
1. **User goes to "Change Password" in their profile**
   ```json
   POST /api/auth/change-password/
   Headers: {
     "Authorization": "Bearer ACCESS_TOKEN"
   }
   Body: {
     "old_password": "CurrentPassword@123",
     "new_password": "NewPassword@456",
### Password Reset Errors
- **Invalid Email**: "No account found with this email address."
- **Expired Code**: "Code has expired. Please request a new one."
- **Invalid Code**: "Invalid verification code."
- **Passwords Don't Match**: "Passwords do not match."
- **Weak Password**: Django validation error messages
- **Rate Limit Exceeded**: HTTP 429 Too Many Requests

### Password Change Errors
- **Not Authenticated**: HTTP 401 Unauthorized
- **Incorrect Current Password**: "Current password is incorrect."
- **Passwords Don't Match**: "New passwords do not match."
- **Same Password**: "New password must be different from current password
2. **System validates and updates password**

3. **User can continue using their session or login again**
   ```

4. **If code expires, user can resend**
   ```json
   POST /api/auth/password-reset/resend/
   {
     "email": "user@example.com"
   }
   ```

## Error Handling

- **Invalid Email**: "No account found with this email addr:
- Password Reset: Sections 7, 8, and 9
- Password Change: Section 10
- **Expired Code**: "Code has expired. Please request a new one."
- **Invalid Code**: "Invalid verification code."
- **Passwords Don't Match**: "Passwords do not match."
- **Weak Password**: Django validation error messages
- **Rate Limit Exceeded**: HTTP 429 Too Many Requests

## Testing

Use the endpoints documented in `INSOMNIA_API_ENDPOINTS.md` sections 7, 8, and 9.

### Password Reset
- Codes are case-sensitive (all digits)
- Each new request overwrites the previous code
- Cache backend is in-memory (for development)
- For production, consider using Redis for cache backend
- Email templates are professional and mobile-responsive

### Password Change
- Requires valid authentication token
- Available to all user types: Admin, Employer, Employee
- Session remains active after password change
- User can optionally logout and login with new password
- For production, consider using Redis for cache backend
- Email templates are professional and mobile-responsive
