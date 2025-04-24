from django.shortcuts import render
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.http import HttpRequest

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

import random
import redis

from .models import User
from .serializers import (
    UserSerializer, 
    UserUpdateSerializer, 
    OTPRequestSerializer, 
    UserRegistrationSerializer,
    CustomTokenObtainPairSerializer,
    LoginSerializer,
    ForgotPasswordRequestSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer
)
from .utils import (
    send_otp_email,
    store_otp,
    verify_otp,
    delete_otp
)
from .constants import ERROR_MESSAGES

# Initialize Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)
OTP_EXPIRY_TIME = 300  # 5 minutes in seconds

# Helper function to generate and send OTP

def generate_and_send_otp(email):
    """Generate a 6-digit OTP and send it via email."""
    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    store_otp(email, otp)
    send_otp_email(email, otp)

@swagger_auto_schema(
    method='post',
    request_body=OTPRequestSerializer,
    responses={
        200: openapi.Response(
            description="OTP sent successfully",
            examples={
                "application/json": {
                    "message": "OTP sent successfully to your email",
                    "email": "user@example.com"
                }
            }
        ),
        400: "Bad Request"
    },
    operation_description="Request OTP for email verification during registration"
)
@api_view(['POST'])
@permission_classes([AllowAny])
def request_otp(request):
    serializer = OTPRequestSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        generate_and_send_otp(email)
        return Response({
            'message': 'OTP sent successfully to your email',
            'email': email
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(
    method='post',
    request_body=UserRegistrationSerializer,
    responses={
        201: openapi.Response(
            description="User registered successfully",
            examples={
                "application/json": {
                    "message": "Registration successful",
                    "user": {
                        "id": 1,
                        "username": "example_user",
                        "email": "user@example.com"
                    }
                }
            }
        ),
        400: "Bad Request"
    },
    operation_description="Register a new user with email verification"
)
@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        provided_otp = serializer.validated_data['otp']
        
        # Verify OTP
        is_valid, error_message = verify_otp(email, provided_otp)
        if not is_valid:
            return Response({
                'error': error_message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create user if OTP is valid
            user = serializer.save()
            
            # Delete used OTP
            delete_otp(email)
            
            return Response({
                'message': 'Registration successful',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            try:
                user = User.objects.get(email=email)
                if not user.check_password(password):
                    return Response({
                        'detail': ERROR_MESSAGES['INVALID_CREDENTIALS']
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                if not user.is_active:
                    return Response({
                        'detail': ERROR_MESSAGES['ACCOUNT_INACTIVE']
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    # 'user': {
                    #     'id': user.id,
                    #     'username': user.username,
                    #     'email': user.email
                    # }
                })
                
            except User.DoesNotExist:
                return Response({
                    'detail': ERROR_MESSAGES['INVALID_CREDENTIALS']
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserUpdateSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            self.perform_update(serializer)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_update(self, serializer):
        serializer.save()

@swagger_auto_schema(
    method='post',
    request_body=ForgotPasswordRequestSerializer,
    responses={
        200: openapi.Response(
            description="Password reset OTP sent",
            examples={
                "application/json": {
                    "message": "Password reset OTP sent successfully to your email",
                    "email": "user@example.com"
                }
            }
        ),
        400: "Bad Request"
    },
    operation_description="Request OTP for password reset"
)
@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_request(request):
    """Request OTP for password reset"""
    serializer = ForgotPasswordRequestSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        generate_and_send_otp(email)
        return Response({
            'message': 'Password reset OTP sent successfully to your email',
            'email': email
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(
    method='post',
    request_body=ResetPasswordSerializer,
    responses={
        200: openapi.Response(
            description="Password reset successful",
            examples={
                "application/json": {
                    "message": "Password reset successful"
                }
            }
        ),
        400: "Bad Request"
    },
    operation_description="Reset password using OTP verification"
)
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    """Reset password with OTP verification"""
    serializer = ResetPasswordSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        provided_otp = serializer.validated_data['otp']
        
        # Verify OTP
        is_valid, error_message = verify_otp(email, provided_otp)
        if not is_valid:
            return Response({
                'error': error_message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get user and update password
            user = User.objects.get(email=email)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            # Delete used OTP
            delete_otp(email)
            
            return Response({
                'message': 'Password reset successful'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(
    method='post',
    request_body=ChangePasswordSerializer,
    responses={
        200: openapi.Response(
            description="Password changed successfully",
            examples={
                "application/json": {
                    "message": "Password changed successfully"
                }
            }
        ),
        400: "Bad Request",
        401: "Unauthorized"
    },
    operation_description="Change password for logged-in user",
    security=[{'Bearer': []}]
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change password for logged-in user"""
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
