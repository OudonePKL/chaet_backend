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
        
        # Log for debugging
        print(f"Message created: {instance.id} in room {room_id} by {instance.sender.username}")
        
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
        
        # Send notifications to other users in the room
        send_notification_to_users(instance.room, instance)

def send_notification_to_users(room, message):
    members = room.members.exclude(id=message.sender.id)
    channel_layer = get_channel_layer()

    for member in members:
        async_to_sync(channel_layer.group_send)(
            f"notifications_{member.id}",  # Match the group name in NotificationConsumer
            {
                "type": "send_notification",  # Match the handler method in NotificationConsumer
                "event": "new_message",
                "room_id": room.id,
                "message_id": message.id,
                "message": message.content,
                "sender": message.sender.username,
                "timestamp": str(message.timestamp),
            },
        )
