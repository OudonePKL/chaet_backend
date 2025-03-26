from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import random
import string
from .models import User
from .serializers import (
    UserSerializer, 
    UserUpdateSerializer, 
    OTPRequestSerializer, 
    UserRegistrationSerializer,
    CustomTokenObtainPairSerializer,
    LoginSerializer
)
import redis
from django.http import HttpRequest
from rest_framework_simplejwt.tokens import RefreshToken

# Initialize Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)
OTP_EXPIRY_TIME = 300  # 5 minutes in seconds

# Create your views here.

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        user.otp = otp
        user.otp_valid_until = timezone.now() + timezone.timedelta(minutes=10)
        user.save()

        # Send verification email
        send_mail(
            'Email Verification',
            f'Your verification code is: {otp}',
            settings.EMAIL_HOST_USER,
            [user.email],
            fail_silently=False,
        )

class VerifyEmailView(generics.GenericAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({
                'detail': 'Email and OTP are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
            print(f"Verifying email for user: {user.email}, Current OTP: {user.otp}, Provided OTP: {otp}")
            
            if user.is_email_verified:
                return Response({
                    'detail': 'Email already verified'
                }, status=status.HTTP_400_BAD_REQUEST)

            if user.otp != otp:
                return Response({
                    'detail': 'Invalid OTP'
                }, status=status.HTTP_400_BAD_REQUEST)

            if user.otp_valid_until < timezone.now():
                return Response({
                    'detail': 'OTP expired'
                }, status=status.HTTP_400_BAD_REQUEST)

            user.is_email_verified = True
            user.otp = None
            user.otp_valid_until = None
            user.save()
            print(f"Email verified successfully for user: {user.email}")

            return Response({
                'detail': 'Email verified successfully',
                'user': {
                    'email': user.email,
                    'is_email_verified': user.is_email_verified,
                    'is_active': user.is_active
                }
            })

        except User.DoesNotExist:
            print(f"User not found with email: {email}")
            return Response({
                'detail': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error verifying email: {str(e)}")
            return Response({
                'detail': f'Error verifying email: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(generics.GenericAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')

        try:
            user = User.objects.get(email=email)
            if user.is_email_verified:
                return Response({'detail': 'Email already verified'}, status=status.HTTP_400_BAD_REQUEST)

            # Generate new OTP
            otp = ''.join(random.choices(string.digits, k=6))
            user.otp = otp
            user.otp_valid_until = timezone.now() + timezone.timedelta(minutes=10)
            user.save()

            # Send verification email
            send_mail(
                'Email Verification',
                f'Your new verification code is: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return Response({'detail': 'New OTP sent successfully'})

        except User.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = (AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            return response
        except Exception as e:
            return Response(
                {'detail': 'Invalid email or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
@api_view(['POST'])
@permission_classes([AllowAny])
def request_otp(request):
    serializer = OTPRequestSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        
        # Generate 6-digit OTP
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Store OTP in Redis with 5 minutes expiry
        redis_client.setex(f"otp:{email}", OTP_EXPIRY_TIME, otp)
        
        # Send OTP via email
        subject = 'Your Chat App Registration OTP'
        message = f'Your OTP for registration is: {otp}\nThis OTP will expire in 5 minutes.'
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [email],
            fail_silently=False,
        )
        
        return Response({
            'message': 'OTP sent successfully to your email',
            'email': email
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        provided_otp = serializer.validated_data['otp']
        
        # Get stored OTP from Redis
        stored_otp = redis_client.get(f"otp:{email}")
        if not stored_otp:
            return Response({
                'error': 'OTP expired or not found. Please request a new OTP.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify OTP
        if provided_otp != stored_otp.decode():
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create user if OTP is valid
            user = serializer.save()
            
            # Delete used OTP
            redis_client.delete(f"otp:{email}")
            
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
                        'detail': 'Invalid email or password'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                if not user.is_active:
                    return Response({
                        'detail': 'Your account is not active'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email
                    }
                })
                
            except User.DoesNotExist:
                return Response({
                    'detail': 'Invalid email or password'
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserUpdateSerializer

    def get_object(self):
        return self.request.user
