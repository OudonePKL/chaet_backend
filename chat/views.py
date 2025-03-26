from django.shortcuts import render
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q
from .models import ChatRoom, Message, Membership
from .serializers import (
    ChatRoomSerializer,
    ChatRoomCreateSerializer,
    MessageSerializer,
    MembershipSerializer,
)
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import random
import redis
from rest_framework import serializers
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# Initialize Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)
OTP_EXPIRY_TIME = 300  # 5 minutes in seconds

# Create your views here.

class ChatRoomListCreateView(generics.ListCreateAPIView):
    """
    List all chat rooms for the authenticated user or create a new chat room.
    """
    permission_classes = (IsAuthenticated,)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ChatRoomCreateSerializer
        return ChatRoomSerializer

    def get_queryset(self):
        return ChatRoom.objects.filter(
            members=self.request.user
        ).order_by('-created_at')

    @swagger_auto_schema(
        operation_description="Create a new chat room",
        request_body=ChatRoomCreateSerializer,
        responses={
            201: ChatRoomSerializer,
            400: "Bad Request"
        }
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

class ChatRoomDetailView(generics.RetrieveAPIView):
    """
    Retrieve details of a specific chat room.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatRoomSerializer
    
    def get_queryset(self):
        return ChatRoom.objects.filter(members=self.request.user)

class MessageListView(generics.ListCreateAPIView):
    """
    List all messages in a chat room or create a new message.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer

    def get_queryset(self):
        room_id = self.kwargs['room_id']
        return Message.objects.filter(
            room_id=room_id,
            room__members=self.request.user
        ).order_by('-timestamp')

    def perform_create(self, serializer):
        room_id = self.kwargs['room_id']
        try:
            room = ChatRoom.objects.get(id=room_id, members=self.request.user)
            serializer.save(sender=self.request.user, room=room)
        except ChatRoom.DoesNotExist:
            raise PermissionError("You don't have access to this chat room")

    @swagger_auto_schema(
        operation_description="Create a new message in the chat room",
        request_body=MessageSerializer,
        responses={
            201: MessageSerializer,
            400: "Bad Request",
            403: "Forbidden"
        }
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

class MembershipViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chat room memberships.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = MembershipSerializer

    def get_queryset(self):
        room_id = self.kwargs['room_id']
        return Membership.objects.filter(
            room_id=room_id,
            room__members=self.request.user
        )

    def perform_create(self, serializer):
        room_id = self.kwargs['room_id']
        try:
            room = ChatRoom.objects.get(id=room_id)
            # Check if the user is an admin
            if not Membership.objects.filter(
                room=room,
                user=self.request.user,
                role='admin'
            ).exists():
                raise PermissionError("Only admins can add members")
            
            # Get user_id from validated data
            user_id = serializer.validated_data.get('user_id')
            if not user_id:
                raise serializers.ValidationError("user_id is required")
            
            # Check if user is already a member
            if Membership.objects.filter(
                room=room,
                user_id=user_id
            ).exists():
                raise serializers.ValidationError("User is already a member of this room")
                
            serializer.save(room=room)
            
        except ChatRoom.DoesNotExist:
            raise PermissionError("Chat room not found")

    @swagger_auto_schema(
        operation_description="Remove yourself from the chat room",
        responses={
            200: "Successfully removed",
            400: "Bad Request",
            404: "Not Found"
        }
    )
    def remove_self(self, request, room_id):
        try:
            room = ChatRoom.objects.get(id=room_id)
            membership = Membership.objects.get(room=room, user=request.user)
            
            # If user is an admin, check if they're the last admin
            if membership.role == 'admin':
                admin_count = Membership.objects.filter(
                    room=room,
                    role='admin'
                ).count()
                if admin_count <= 1:
                    # If they're the last admin, delete the entire room
                    room.delete()
                    return Response(
                        {"detail": "Successfully removed yourself and deleted the room"},
                        status=status.HTTP_200_OK
                    )
            
            # If not the last admin or not an admin, just remove the membership
            membership.delete()
            return Response(
                {"detail": "Successfully removed yourself from the room"},
                status=status.HTTP_200_OK
            )
            
        except ChatRoom.DoesNotExist:
            return Response(
                {"error": "Chat room not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "You are not a member of this room"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @swagger_auto_schema(
        operation_description="Remove another member from the chat room (admin only)",
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_PATH,
                description="ID of the user to remove",
                type=openapi.TYPE_INTEGER,
                required=True
            )
        ],
        responses={
            200: "Successfully removed",
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found"
        }
    )
    def remove_member(self, request, room_id, user_id):
        try:
            room = ChatRoom.objects.get(id=room_id)
            
            # Check if requester is admin
            if not Membership.objects.filter(
                room=room,
                user=request.user,
                role='admin'
            ).exists():
                return Response(
                    {"warning": "Only admins can remove other members from the room"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get the membership to be removed
            membership = Membership.objects.get(room=room, user_id=user_id)
            
            # Prevent removing the last admin
            if membership.role == 'admin':
                admin_count = Membership.objects.filter(
                    room=room,
                    role='admin'
                ).count()
                if admin_count <= 1:
                    return Response(
                        {"warning": "Cannot remove the last admin from the room"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            membership.delete()
            return Response(
                {"detail": "Successfully removed member from the room"},
                status=status.HTTP_200_OK
            )
            
        except ChatRoom.DoesNotExist:
            return Response(
                {"error": "Chat room not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Membership.DoesNotExist:
            return Response(
                {"error": "User is not a member of this room"},
                status=status.HTTP_400_BAD_REQUEST
            )

class DirectChatView(generics.GenericAPIView):
    """
    Create or retrieve a direct chat with another user.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatRoomSerializer

    @swagger_auto_schema(
        operation_description="Create or retrieve a direct chat with another user",
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_PATH,
                description="ID of the user to start/retrieve direct chat with",
                type=openapi.TYPE_INTEGER,
                required=True
            )
        ],
        responses={
            200: ChatRoomSerializer,
            201: ChatRoomSerializer,
            400: "Bad Request"
        }
    )
    def post(self, request, user_id):
        try:
            # Check if direct chat already exists
            existing_chat = ChatRoom.objects.filter(
                type='direct',
                members=request.user
            ).filter(
                members=user_id
            ).first()

            if existing_chat:
                serializer = self.get_serializer(existing_chat)
                return Response(serializer.data)

            # Create new direct chat
            chat_room = ChatRoom.objects.create(type='direct')
            Membership.objects.create(user=request.user, room=chat_room, role='admin')
            Membership.objects.create(user_id=user_id, room=chat_room, role='admin')

            serializer = self.get_serializer(chat_room)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
