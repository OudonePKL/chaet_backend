import json
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token_key):
    """
    Validate JWT token and return user
    """
    if not token_key:
        return AnonymousUser()
    
    try:
        access_token = AccessToken(token_key)
        return User.objects.get(id=access_token['user_id'])
    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    JWT middleware for WebSocket authentication
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Get token from query string or headers
        token_key = None
        
        # Check query string first
        query_string = parse_qs(scope.get('query_string', b'').decode())
        if 'token' in query_string:
            token_key = query_string['token'][0]
        
        # Fallback to authorization header
        if not token_key and 'headers' in scope:
            headers = dict(scope['headers'])
            if b'authorization' in headers:
                auth_header = headers[b'authorization'].decode()
                if auth_header.startswith('Bearer '):
                    token_key = auth_header.split(' ')[1]
        
        # Authenticate user
        scope['user'] = await get_user_from_token(token_key)
        
        return await self.app(scope, receive, send)

def JWTAuthMiddlewareStack(inner):
    """
    Helper to return properly configured middleware stack
    """
    return JWTAuthMiddleware(inner)