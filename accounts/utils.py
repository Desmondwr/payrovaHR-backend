from rest_framework.views import exception_handler
from rest_framework.response import Response
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.core.cache import cache
import pyotp
import qrcode
import io
import base64
import random
import string


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent API responses"""
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response = {
            'success': False,
            'message': 'An error occurred',
            'data': None,
            'errors': []
        }
        
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                custom_response['message'] = str(response.data['detail'])
            else:
                custom_response['errors'] = response.data
        elif isinstance(response.data, list):
            custom_response['errors'] = response.data
        else:
            custom_response['message'] = str(response.data)
        
        response.data = custom_response
    
    return response


def send_activation_email(user, activation_token):
    """Send activation email to the employer"""
    activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token.token}"
    
    context = {
        'user': user,
        'activation_link': activation_link,
        'activation_code': activation_token.token,
        'expiry_hours': settings.ACTIVATION_TOKEN_EXPIRY_HOURS,
    }
    
    # Render HTML email
    html_message = render_to_string('emails/activation_email.html', context)
    plain_message = render_to_string('emails/activation_email.txt', context)
    
    subject = 'Activate Your HR Account'
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending activation email: {str(e)}")
        return False


def generate_totp_secret():
    """Generate a new TOTP secret for 2FA"""
    return pyotp.random_base32()


def generate_qr_code(secret, email):
    """Generate QR code for TOTP setup"""
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name='Payrova HR'
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def verify_totp_code(secret, code):
    """Verify TOTP code"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def api_response(success=True, message='', data=None, errors=None, status=200):
    """Consistent API response format"""
    response_data = {
        'success': success,
        'message': message,
        'data': data if data is not None else {},
        'errors': errors if errors is not None else []
    }
    return Response(response_data, status=status)


def generate_reset_code():
    """Generate a 6-digit random code for password reset"""
    return ''.join(random.choices(string.digits, k=6))


def send_password_reset_email(email, code):
    """Send password reset code to user's email"""
    context = {
        'code': code,
    }
    
    # Render HTML and plain text email
    html_message = render_to_string('emails/password_reset_code.html', context)
    plain_message = render_to_string('emails/password_reset_code.txt', context)
    
    subject = 'Password Reset Code - PayrovaHR'
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending password reset email: {str(e)}")
        return False


def store_reset_code(email, code):
    """Store reset code in cache with 5 minute expiry"""
    cache_key = f"password_reset_{email}"
    cache.set(cache_key, code, timeout=300)  # 5 minutes = 300 seconds


def verify_reset_code(email, code):
    """Verify reset code from cache"""
    cache_key = f"password_reset_{email}"
    stored_code = cache.get(cache_key)
    
    if stored_code is None:
        return False, "Code has expired. Please request a new one."
    
    if stored_code != code:
        return False, "Invalid verification code."
    
    return True, "Code verified successfully."


def delete_reset_code(email):
    """Delete reset code from cache after successful password reset"""
    cache_key = f"password_reset_{email}"
    cache.delete(cache_key)

