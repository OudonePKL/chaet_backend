from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserProfileView,
    request_otp,
    register_user,
    LoginView
)

urlpatterns = [
    # Authentication URLs
    path('request-otp/', request_otp, name='request-otp'),
    path('register/', register_user, name='register'),
    path('token/', LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # User URLs
    path('profile/', UserProfileView.as_view(), name='user-profile'),
] 