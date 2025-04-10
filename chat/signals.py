from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Message

@receiver(post_save, sender=Message)
def send_message_notification(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        room_id = instance.room.id
        data = {
            'type': 'new_message',
            'message': {
                'id': instance.id,
                'sender': instance.sender.username,
                'content': instance.content,
                'timestamp': instance.timestamp.isoformat(),
                'status': instance.status,
            }
        }
        async_to_sync(channel_layer.group_send)(
            f"chatroom_{room_id}",
            data
        )
