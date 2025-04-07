import redis
from django.core.mail import send_mail
from django.conf import settings
from .constants import (
    REDIS_HOST, REDIS_PORT, REDIS_DB,
    OTP_EXPIRY_TIME,
    EMAIL_SUBJECT, EMAIL_MESSAGE_TEMPLATE,
    ERROR_MESSAGES
)

# Initialize Redis connection
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def set_user_online(user_id):
    redis_client.set(f'user:{user_id}:online', 'true', ex=300)  # 5 minute timeout

def set_user_offline(user_id):
    redis_client.delete(f'user:{user_id}:online')

def is_user_online(user_id):
    return redis_client.exists(f'user:{user_id}:online') == 1

def send_otp_email(email, otp):
    """Send OTP via email."""
    message = EMAIL_MESSAGE_TEMPLATE.format(otp=otp)
    return send_mail(
        EMAIL_SUBJECT,
        message,
        settings.EMAIL_HOST_USER,
        [email],
        fail_silently=False,
    )

def store_otp(email, otp):
    """Store OTP in Redis with expiry."""
    redis_client.setex(f"otp:{email}", OTP_EXPIRY_TIME, otp)

def get_stored_otp(email):
    """Get stored OTP from Redis."""
    return redis_client.get(f"otp:{email}")

def delete_otp(email):
    """Delete OTP from Redis."""
    redis_client.delete(f"otp:{email}")

def verify_otp(email, provided_otp):
    """Verify OTP against stored value."""
    stored_otp = get_stored_otp(email)
    if not stored_otp:
        return False, ERROR_MESSAGES['OTP_EXPIRED']
    
    if provided_otp != stored_otp.decode():
        return False, ERROR_MESSAGES['INVALID_OTP']
    
    return True, None 


