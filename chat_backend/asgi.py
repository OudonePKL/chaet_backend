"""
ASGI config for chat_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import jwt
import logging
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from chat.routing import websocket_urlpatterns
from django.conf import settings
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat_backend.settings')

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        try:
            # Get token from query string or headers
            query_string = scope.get('query_string', b'').decode()
            query_params = parse_qs(query_string)
            
            headers = dict(scope['headers'])
            token = None

            # Try to get token from headers first
            if b'authorization' in headers:
                auth_header = headers[b'authorization'].decode()
                if auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
                    logger.info("Found token in Authorization header")

            # If no token in headers, try query string
            if not token and 'token' in query_params:
                token = query_params['token'][0]
                logger.info("Found token in query parameters")

            if token:
                try:
                    # Decode JWT token
                    payload = jwt.decode(
                        token,
                        settings.SECRET_KEY,
                        algorithms=['HS256']
                    )
                    User = get_user_model()
                    user = await User.objects.filter(id=payload['user_id']).afirst()
                    if user:
                        logger.info(f"Authenticated user {user.username}")
                        scope['user'] = user
                        return await super().__call__(scope, receive, send)
                except jwt.ExpiredSignatureError:
                    logger.warning("Token has expired")
                except jwt.InvalidTokenError as e:
                    logger.warning(f"Invalid token: {str(e)}")
                except Exception as e:
                    logger.error(f"Authentication error: {str(e)}")
            else:
                logger.warning("No token provided")

            # If authentication fails, set AnonymousUser
            scope['user'] = AnonymousUser()
            return await super().__call__(scope, receive, send)
            
        except Exception as e:
            logger.error(f"Middleware error: {str(e)}")
            scope['user'] = AnonymousUser()
            return await super().__call__(scope, receive, send)

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
