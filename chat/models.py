from django.db import models
from django.utils import timezone
from users.models import User

class ChatRoom(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(
        max_length=10,
        choices=[('direct', 'Direct'), ('group', 'Group')],
        default='direct'
    )
    created_at = models.DateTimeField(default=timezone.now)
    members = models.ManyToManyField(User, through='Membership', related_name='chat_rooms')

    def __str__(self):
        return self.name or f"Chat {self.id}"

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=10,
        choices=[('admin', 'Admin'), ('member', 'Member')],
        default='member'
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'room')

class Message(models.Model):
    content = models.TextField()
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=10,
        choices=[('sending', 'Sending'), ('delivered', 'Delivered'), ('seen', 'Seen')],
        default='sending'
    )

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"
