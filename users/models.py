from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

def validate_image_size(value):
    filesize = value.size
    if filesize > 5 * 1024 * 1024:  # 5MB limit
        raise ValidationError("Maximum file size is 5MB")

class User(AbstractUser):
    email = models.EmailField(unique=True)
    profile_pic = models.ImageField(
        upload_to='profile_pics/', 
        null=True, 
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif']),
            validate_image_size
        ],
        help_text="Profile picture (max 5MB, formats: jpg, jpeg, png, gif)"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['username']),
        ]

    def __str__(self):
        return f"{self.username} ({self.email})"

    def get_chat_rooms(self):
        """
        Get all chat rooms where user is a member
        """
        return self.chat_rooms.all()

    def get_direct_chats(self):
        """
        Get all direct chat rooms
        """
        return self.chat_rooms.filter(type='direct')

    def get_group_chats(self):
        """
        Get all group chat rooms
        """
        return self.chat_rooms.filter(type='group')
