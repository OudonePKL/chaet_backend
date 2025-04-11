import json
import logging
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from .models import ChatRoom, Message, Membership

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def update_user_status(self, status):
        """Update user's status in the room"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_status',
                'user': self.user.username,
                'status': status,
                'timestamp': timezone.now().isoformat()
            }
        )

    async def update_typing_status(self, is_typing):
        """Send typing status to room group"""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status',
                'user': self.user.username,
                'is_typing': is_typing,
                'timestamp': timezone.now().isoformat()
            }
        )

    async def update_message_status(self, message_id, status):
        """Update message status in database and broadcast to room"""
        try:
            # Update message status in database
            message = await sync_to_async(Message.objects.get)(id=message_id)
            message.status = status
            await sync_to_async(message.save)()

            # Broadcast status update to room
            await self.channel_layer.group_send(
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

    async def connect(self):
        """Handle WebSocket connection"""
        try:
            # Get the user from the scope (set by JWTAuthMiddleware)
            self.user = self.scope['user']
            
            # Check if user is authenticated
            if isinstance(self.user, AnonymousUser):
                logger.warning("Unauthenticated user tried to connect")
                await self.close(code=4001)
                return
                
            # Get room ID from the URL route
            self.room_id = self.scope['url_route']['kwargs']['room_id']
            
            # Verify room exists and user is a member
            try:
                self.room = await sync_to_async(ChatRoom.objects.get)(id=self.room_id)
                is_member = await sync_to_async(self.room.members.filter(id=self.user.id).exists)()
                if not is_member:
                    logger.warning(f"User {self.user.username} tried to join room {self.room_id} without membership")
                    await self.close(code=4002)
                    return
            except ChatRoom.DoesNotExist:
                logger.warning(f"Attempted to connect to non-existent room {self.room_id}")
                await self.close(code=4004)
                return
                
            self.room_group_name = f'chat_{self.room_id}'
            
            logger.info(f"User {self.user.username} attempting to connect to room {self.room_id}")
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Accept the connection
            await self.accept()
            
            # Send last 50 messages
            messages = await sync_to_async(list)(
                Message.objects.filter(room=self.room)
                .order_by('-timestamp')[:50]
                .select_related('sender')
            )
            
            for message in reversed(messages):
                await self.send(text_data=json.dumps({
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
                    await self.update_message_status(message.id, 'delivered')
            
            # Send join message and update user status
            await self.channel_layer.group_send(
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
            await self.update_user_status('online')
            
            logger.info(f"User {self.user.username} successfully connected to room {self.room_id}")
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}")
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        try:
            if hasattr(self, 'room_group_name') and hasattr(self, 'user'):
                # Update user status to offline
                await self.update_user_status('offline')
                
                # Clear typing status when user disconnects
                await self.update_typing_status(False)
                
                # Send leave message to room group
                await self.channel_layer.group_send(
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
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                
                logger.info(f"User {self.user.username} disconnected from room {self.room_id} with code: {close_code}")
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'status':
                # Handle status update
                status = text_data_json.get('status')
                if status in ['online', 'offline', 'away']:
                    await self.update_user_status(status)
                return
            
            elif message_type == 'typing':
                # Handle typing status
                is_typing = text_data_json.get('is_typing', False)
                await self.update_typing_status(is_typing)
                return

            elif message_type == 'read_receipt':
                # Handle read receipt
                message_id = text_data_json.get('message_id')
                if message_id:
                    await self.update_message_status(message_id, 'seen')
                return
                
            message_content = text_data_json.get('message', '')
            logger.info(f"Received message from {self.user.username} in room {self.room_id}: {message_content}")

            # Clear typing status when message is sent
            await self.update_typing_status(False)

            # Save message to database with initial status 'sending'
            message = await sync_to_async(Message.objects.create)(
                content=message_content,
                sender=self.user,
                room=self.room,
                status='sending',
                timestamp=timezone.now()
            )

            # Send message to room group
            await self.channel_layer.group_send(
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
            await self.update_message_status(message.id, 'sent')

        except Exception as e:
            logger.error(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    # Handler methods for different message types
    async def chat_message(self, event):
        """Handle chat messages from the group"""
        try:
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
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
                await self.update_message_status(event['message_id'], 'delivered')

        except Exception as e:
            logger.error(f"Error in chat_message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def user_status(self, event):
        """Handle user status updates from the group"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'user.status',
                'user': event['user'],
                'status': event['status'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in user_status: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def typing_status(self, event):
        """Handle typing status updates from the group"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'typing.status',
                'user': event['user'],
                'is_typing': event['is_typing'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in typing_status: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def message_status(self, event):
        """Handle message status updates from the group"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'message.status',
                'message_id': event['message_id'],
                'status': event['status'],
                'user': event['user'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in message_status: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        self.group_name = f'notifications_{self.user.id}'

        # Join user-specific notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"User {self.user.username} connected to NotificationConsumer")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.username} disconnected from NotificationConsumer")

    async def receive_json(self, content):
        # Optional: Handle client pings or request actions here
        action = content.get("action")
        if action == "ping":
            await self.send_json({
                "type": "pong",
                "timestamp": timezone.now().isoformat()
            })

    async def send_notification(self, event):
        """
        Handler for notification messages sent via channel layer.
        Example usage from signal or backend:
            channel_layer.group_send(
                f'notifications_{user_id}',
                {
                    'type': 'send.notification',
                    'event': 'new_message',
                    'room_id': 1,
                    'message_id': 5,
                    'message': 'You have a new message',
                    'timestamp': '2024-01-01T12:00:00Z'
                }
            )
        """
        await self.send_json({
            "type": "notification",
            "event": event.get("event"),
            "room_id": event.get("room_id"),
            "message_id": event.get("message_id"),
            "message": event.get("message"),
            "timestamp": event.get("timestamp")
        })
