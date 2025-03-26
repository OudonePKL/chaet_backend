from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    def validate(self, attrs):
        try:
            email = attrs.get('email')
            password = attrs.get('password')
            
            if not email or not password:
                raise serializers.ValidationError({
                    'detail': 'Email and password are required'
                })

            # First try to get the user by email
            try:
                user = User.objects.get(email=email)
                print(f"Found user: {user.email}, is_active: {user.is_active}")
                
                # Check if password is correct
                if not user.check_password(password):
                    print(f"Invalid password for user: {user.email}")
                    raise serializers.ValidationError({
                        'detail': 'Invalid email or password'
                    })
                
            except User.DoesNotExist:
                print(f"User not found with email: {email}")
                raise serializers.ValidationError({
                    'detail': 'Invalid email or password'
                })
            
            # Check if user is active
            if not user.is_active:
                print(f"User account not active: {user.email}")
                raise serializers.ValidationError({
                    'detail': 'Your account is not active. Please contact support.'
                })
            
            # If all checks pass, proceed with token generation
            try:
                # Set the user in the serializer instance
                self.user = user
                data = super().validate(attrs)
                data['email'] = self.user.email
                data['username'] = self.user.username
                print(f"Successfully generated token for user: {self.user.email}")
                return data
            except Exception as e:
                print(f"Error generating token: {str(e)}")
                raise serializers.ValidationError({
                    'detail': f'Error generating token: {str(e)}'
                })
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            print(f"Unexpected error in validate: {str(e)}")
            raise serializers.ValidationError({
                'detail': f'Authentication failed: {str(e)}'
            })

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 'profile_pic', 'status', 'last_seen', 'created_at')
        read_only_fields = ('status', 'last_seen', 'created_at')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        if 'profile_pic' in validated_data:
            user.profile_pic = validated_data['profile_pic']
            user.save()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'profile_pic')
        read_only_fields = ('email',)

class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Check if email already exists
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")
        return value

class UserRegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={'input_type': 'password'}, write_only=True)
    otp = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'otp']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Passwords must match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        validated_data.pop('otp')  # Remove OTP from validated_data
        
        # Create user with both is_active set to True
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            is_active=True,
        )
        return user 