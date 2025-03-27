from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Chat API",
        default_version='v1',
        description="""
        API documentation for the Chat Application.
        
        ## Authentication
        The API uses JWT (JSON Web Token) for authentication. To use authenticated endpoints:
        1. Login using the `/api/v1/users/token/` endpoint
        2. Copy the access token from the response
        3. Add it to the Authorization header as 'Bearer <token>'
        
        ## Endpoints
        - `/api/v1/users/`: User management endpoints
        - `/api/v1/chat/`: Chat functionality endpoints
        """,
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@chat.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=[
        path('api/v1/users/', include('users.urls')),
        path('api/v1/chat/', include('chat.urls')),
    ],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/chat/', include('chat.urls')),
    
    # Swagger URLs
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Add media URL patterns in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
