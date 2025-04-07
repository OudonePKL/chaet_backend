from django.db import models
from django.utils import timezone
from django.db.models import Q
from users.models import User
from django.core.exceptions import ValidationError

class ChatRoom(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(
        max_length=10,
        choices=[('direct', 'Direct'), ('group', 'Group')],
        default='direct'
    )
    created_at = models.DateTimeField(default=timezone.now)
    members = models.ManyToManyField(User, through='Membership', related_name='chat_rooms')

    class Meta:
        constraints = [
            # Prevent duplicate direct chats between same users
            models.UniqueConstraint(
                fields=['type'],
                condition=Q(type='direct'),
                name='unique_direct_chat_per_user_pair'
            )
        ]

    def __str__(self):
        if self.type == 'direct':
            other_user = self.members.exclude(id=self.get_other_member_id()).first()
            return f"Direct chat with {other_user.username}"
        return self.name or f"Group Chat {self.id}"

    def save(self, *args, **kwargs):
        if self.type == 'direct':
            self.name = None  # Direct chats shouldn't have names
        elif not self.name:
            raise ValueError("Group chats must have a name")
        super().save(*args, **kwargs)

    def get_other_member_id(self, user=None):
        """For direct chats, get the other member's ID"""
        if self.type != 'direct':
            return None
        user = user or self.context.get('request').user
        return self.members.exclude(id=user.id).first().id

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(
        max_length=10,
        choices=[('admin', 'Admin'), ('member', 'Member')],
        default='member'
    )
    joined_at = models.DateTimeField(default=timezone.now)
    last_role_change = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'room')

    def save(self, *args, **kwargs):
        if self.pk:  # Only update last_role_change if role is being updated
            original = Membership.objects.get(pk=self.pk)
            if original.role != self.role:
                self.last_role_change = timezone.now()
        super().save(*args, **kwargs)

class Message(models.Model):
    content = models.TextField()
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=10,
        choices=[('sending', 'Sending'), ('delivered', 'Delivered'), ('seen', 'Seen')],
        default='sending'
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ManyToManyField(User, related_name='read_messages', blank=True)
    attachment = models.FileField(upload_to='message_attachments/%Y/%m/%d/', null=True, blank=True)
    attachment_type = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['room', 'timestamp']),
            models.Index(fields=['status']),
        ]
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"

    def delete(self, soft_delete=True, *args, **kwargs):
        if soft_delete:
            self.deleted_at = timezone.now()
            self.save()
        else:
            super().delete(*args, **kwargs)

    def is_deleted(self):
        return self.deleted_at is not None

    def get_attachment_url(self):
        if self.attachment:
            return self.attachment.url
        return None

class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)  # Consider using EmojiField if needed
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji')

    def clean(self):
        # Add emoji validation if needed
        if not self.emoji:
            raise ValidationError("Emoji is required")
        super().clean()