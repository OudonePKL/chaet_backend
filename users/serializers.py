from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .constants import ERROR_MESSAGES
from .utils import is_user_online 

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
                
                # Check if password is correct
                if not user.check_password(password):
                    raise serializers.ValidationError({
                        'detail': ERROR_MESSAGES['INVALID_CREDENTIALS']
                    })
                
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'detail': ERROR_MESSAGES['INVALID_CREDENTIALS']
                })
            
            # Check if user is active
            if not user.is_active:
                raise serializers.ValidationError({
                    'detail': ERROR_MESSAGES['ACCOUNT_INACTIVE']
                })
            
            # If all checks pass, proceed with token generation
            try:
                # Set the user in the serializer instance
                self.user = user
                data = super().validate(attrs)
                data['email'] = self.user.email
                data['username'] = self.user.username
                return data
            except Exception as e:
                raise serializers.ValidationError({
                    'detail': f'Error generating token: {str(e)}'
                })
            
        except serializers.ValidationError:
            raise
        except Exception as e:
            raise serializers.ValidationError({
                'detail': f'Authentication failed: {str(e)}'
            })

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    is_online = serializers.SerializerMethodField()

    profile_pic = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 'profile_pic', 'status', 'last_seen', 'created_at', 'is_online')
        read_only_fields = ('status', 'last_seen', 'created_at', 'is_online')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({"password": ERROR_MESSAGES['PASSWORD_MISMATCH']})
        return attrs
    
    def get_is_online(self, obj):
        return is_user_online(obj.id)

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
    
    def get_profile_pic(self, obj):
        request = self.context.get('request')
        if obj.profile_pic and request:
            return request.build_absolute_uri(obj.profile_pic.url)
        return None

class UserUpdateSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'profile_pic')
        read_only_fields = ('email',)

    def update(self, instance, validated_data):
        # Handle profile pic update
        if 'profile_pic' in validated_data:
            # Delete old profile pic if it exists
            if instance.profile_pic:
                instance.profile_pic.delete(save=False)
            
        instance.username = validated_data.get('username', instance.username)
        instance.profile_pic = validated_data.get('profile_pic', instance.profile_pic)
        instance.save()
        return instance

class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Check if email already exists
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(ERROR_MESSAGES['EMAIL_EXISTS'])
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
            raise serializers.ValidationError({'password': ERROR_MESSAGES['PASSWORD_MISMATCH']})
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

class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Check if email exists
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No account found with this email address")
        return value

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'password': ERROR_MESSAGES['PASSWORD_MISMATCH']})
        return data

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    confirm_password = serializers.CharField()

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect")
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'password': ERROR_MESSAGES['PASSWORD_MISMATCH']})
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user 