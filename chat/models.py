from django.db import models
from django.utils import timezone
from django.db.models import Q
from users.models import User


class ChatRoom(models.Model):
    TYPE_CHOICES = [
        ('direct', 'Direct'),
        ('group', 'Group'),
    ]

    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='direct')
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(User, through='Membership', related_name='chat_rooms')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['type'],
                condition=Q(type='direct'),
                name='unique_direct_chat_type'  # Note: this doesn't enforce per-user uniqueness
            ),
        ]

    def __str__(self):
        if self.type == 'direct':
            try:
                other_user = self.members.exclude(id=self._current_user_id).first()
                return f"Direct chat with {other_user.username}" if other_user else "Direct Chat"
            except:
                return "Direct Chat"
        return self.name or f"Group Chat {self.id}"

    def save(self, *args, **kwargs):
        if self.type == 'direct':
            self.name = None
        elif not self.name:
            raise ValueError("Group chats must have a name")
        super().save(*args, **kwargs)

    def get_other_member_id(self, user):
        """
        For direct chats, get the other member's ID, excluding the provided user.
        """
        if self.type != 'direct':
            return None
        other = self.members.exclude(id=user.id).first()
        return other.id if other else None


class Membership(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    last_role_change = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'room')

    def save(self, *args, **kwargs):
        if self.pk:
            original = Membership.objects.get(pk=self.pk)
            if original.role != self.role:
                self.last_role_change = timezone.now()
        super().save(*args, **kwargs)


class Message(models.Model):
    STATUS_CHOICES = [
        ('sending', 'Sending'),
        ('delivered', 'Delivered'),
        ('seen', 'Seen'),
    ]

    content = models.TextField()
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sending')
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
        return self.attachment.url if self.attachment else None
