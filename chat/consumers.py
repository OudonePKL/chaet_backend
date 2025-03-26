import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from .models import ChatRoom, Message
import logging

logger = logging.getLogger(__name__)

class ChatConsumer(WebsocketConsumer):
    def update_user_status(self, status):
        # Update user's status in the room
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'user_status',
                'user': self.user.username,
                'status': status,
                'timestamp': timezone.now().isoformat()
            }
        )

    def update_typing_status(self, is_typing):
        # Send typing status to room group
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'typing_status',
                'user': self.user.username,
                'is_typing': is_typing,
                'timestamp': timezone.now().isoformat()
            }
        )

    def update_message_status(self, message_id, status):
        try:
            # Update message status in database
            message = Message.objects.get(id=message_id)
            message.status = status
            message.save()

            # Broadcast status update to room
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'message_status',
                    'message_id': message_id,
                    'status': status,
                    'user': self.user.username,
                    'timestamp': timezone.now().isoformat()
                }
            )
            logger.info(f"Message {message_id} status updated to {status} by {self.user.username}")
        except Message.DoesNotExist:
            logger.error(f"Message {message_id} not found")
        except Exception as e:
            logger.error(f"Error updating message status: {str(e)}")

    def connect(self):
        try:
            # Get the user from the scope (set by JWTAuthMiddleware)
            self.user = self.scope['user']
            
            # Check if user is authenticated
            if isinstance(self.user, AnonymousUser):
                logger.warning("Unauthenticated user tried to connect")
                self.close(code=4001)
                return
                
            # Get room ID from the URL route
            self.room_id = self.scope['url_route']['kwargs']['room_id']
            
            # Verify room exists and user is a member
            try:
                self.room = ChatRoom.objects.get(id=self.room_id)
                if not self.room.members.filter(id=self.user.id).exists():
                    logger.warning(f"User {self.user.username} tried to join room {self.room_id} without membership")
                    self.close(code=4002)
                    return
            except ChatRoom.DoesNotExist:
                logger.warning(f"Attempted to connect to non-existent room {self.room_id}")
                self.close(code=4004)
                return
                
            self.room_group_name = f'chat_{self.room_id}'
            
            logger.info(f"User {self.user.username} attempting to connect to room {self.room_id}")
            
            # Join room group
            async_to_sync(self.channel_layer.group_add)(
                self.room_group_name,
                self.channel_name
            )
            
            # Accept the connection
            self.accept()
            
            # Send last 50 messages
            messages = Message.objects.filter(room=self.room).order_by('-timestamp')[:50]
            for message in reversed(messages):
                self.send(text_data=json.dumps({
                    'type': 'chat.message',
                    'message_id': message.id,
                    'message': message.content,
                    'user': message.sender.username,
                    'message_type': 'message',
                    'status': message.status,
                    'timestamp': message.timestamp.isoformat()
                }))
                # Mark messages as delivered for this user
                if message.sender != self.user and message.status == 'sent':
                    self.update_message_status(message.id, 'delivered')
            
            # Send join message and update user status
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': f"{self.user.username} joined the chat",
                    'user': self.user.username,
                    'message_type': 'join',
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            # Update user status to online
            self.update_user_status('online')
            
            logger.info(f"User {self.user.username} successfully connected to room {self.room_id}")
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}")
            self.close(code=4000)

    def disconnect(self, close_code):
        try:
            if hasattr(self, 'room_group_name') and hasattr(self, 'user'):
                # Update user status to offline
                self.update_user_status('offline')
                
                # Clear typing status when user disconnects
                self.update_typing_status(False)
                
                # Send leave message to room group
                async_to_sync(self.channel_layer.group_send)(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': f"{self.user.username} left the chat",
                        'user': self.user.username,
                        'message_type': 'leave',
                        'timestamp': timezone.now().isoformat()
                    }
                )
                
                # Leave room group
                async_to_sync(self.channel_layer.group_discard)(
                    self.room_group_name,
                    self.channel_name
                )
                
                logger.info(f"User {self.user.username} disconnected from room {self.room_id} with code: {close_code}")
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}")

    def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'status':
                # Handle status update
                status = text_data_json.get('status')
                if status in ['online', 'offline', 'away']:
                    self.update_user_status(status)
                return
            
            elif message_type == 'typing':
                # Handle typing status
                is_typing = text_data_json.get('is_typing', False)
                self.update_typing_status(is_typing)
                return

            elif message_type == 'read_receipt':
                # Handle read receipt
                message_id = text_data_json.get('message_id')
                if message_id:
                    self.update_message_status(message_id, 'seen')
                return
                
            message_content = text_data_json.get('message', '')
            logger.info(f"Received message from {self.user.username} in room {self.room_id}: {message_content}")

            # Clear typing status when message is sent
            self.update_typing_status(False)

            # Save message to database with initial status 'sending'
            message = Message.objects.create(
                content=message_content,
                sender=self.user,
                room=self.room,
                status='sending',
                timestamp=timezone.now()
            )

            # Send message to room group
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': message.id,
                    'message': message_content,
                    'user': self.user.username,
                    'message_type': 'message',
                    'status': 'sent',
                    'timestamp': message.timestamp.isoformat()
                }
            )

            # Update message status to 'sent'
            self.update_message_status(message.id, 'sent')

        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    def chat_message(self, event):
        try:
            # Send message to WebSocket
            self.send(text_data=json.dumps({
                'type': 'chat.message',
                'message_id': event.get('message_id'),
                'message': event['message'],
                'user': event['user'],
                'message_type': event['message_type'],
                'status': event.get('status'),
                'timestamp': event['timestamp']
            }))

            # If this is a new message and recipient is not the sender, mark as delivered
            if (event['message_type'] == 'message' and 
                event['user'] != self.user.username and 
                event.get('status') == 'sent'):
                self.update_message_status(event['message_id'], 'delivered')

        except Exception as e:
            logger.error(f"Error in chat_message: {str(e)}")
            self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    def user_status(self, event):
        try:
            # Send status update to WebSocket
            self.send(text_data=json.dumps({
                'type': 'user.status',
                'user': event['user'],
                'status': event['status'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in user_status: {str(e)}")
            self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    def typing_status(self, event):
        try:
            # Send typing status to WebSocket
            self.send(text_data=json.dumps({
                'type': 'typing.status',
                'user': event['user'],
                'is_typing': event['is_typing'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in typing_status: {str(e)}")
            self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    def message_status(self, event):
        try:
            # Send message status update to WebSocket
            self.send(text_data=json.dumps({
                'type': 'message.status',
                'message_id': event['message_id'],
                'status': event['status'],
                'user': event['user'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in message_status: {str(e)}")
            self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            })) 