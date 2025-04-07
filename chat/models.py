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
    
    def save(self, *args, **kwargs):
        if self.type == 'group' and not self.name:
            raise ValueError("Group chats must have a name.")
        super().save(*args, **kwargs)

    def is_direct_chat(self):
        return self.type == 'direct' and self.members.count() == 2

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="memberships")
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
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(
        max_length=10,
        choices=[('sending', 'Sending'), ('delivered', 'Delivered'), ('seen', 'Seen')],
        default='sending'
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    read_by = models.ManyToManyField(User, related_name='read_messages', blank=True)
    attachment = models.FileField(upload_to='message_attachments/', null=True, blank=True)
    attachment_type = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"

class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji')