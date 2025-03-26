from django.conf import settings

# Redis settings
REDIS_HOST = getattr(settings, 'REDIS_HOST', 'localhost')
REDIS_PORT = getattr(settings, 'REDIS_PORT', 6379)
REDIS_DB = getattr(settings, 'REDIS_DB', 0)

# OTP settings
OTP_EXPIRY_TIME = 300  # 5 minutes in seconds

# Email settings
EMAIL_SUBJECT = 'Your Chat App Registration OTP'
EMAIL_MESSAGE_TEMPLATE = 'Your OTP for registration is: {otp}\nThis OTP will expire in 5 minutes.'

# Error messages
ERROR_MESSAGES = {
    'INVALID_CREDENTIALS': 'Invalid email or password',
    'ACCOUNT_INACTIVE': 'Your account is not active. Please contact support.',
    'OTP_EXPIRED': 'OTP expired or not found. Please request a new OTP.',
    'INVALID_OTP': 'Invalid OTP',
    'EMAIL_EXISTS': 'Email already registered',
    'PASSWORD_MISMATCH': "Password fields didn't match.",
    'USER_EXISTS': 'User is already a member of this room',
    'ROOM_NOT_FOUND': 'Chat room not found',
    'ADMIN_ONLY': 'Only admins can add members',
} 