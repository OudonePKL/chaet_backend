from django.shortcuts import render, get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsMessageOwner
from django.db.models import Q, Prefetch
from django.db import transaction
from rest_framework.throttling import ScopedRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from .models import ChatRoom, Message, Membership
from users.models import User
from .serializers import (
    ChatRoomSerializer,
    ChatRoomCreateSerializer,
    MessageSerializer,
    MembershipSerializer
)
from users.serializers import UserSerializer
import redis
from rest_framework.exceptions import PermissionDenied
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from functools import wraps
import pickle
from rest_framework.filters import SearchFilter
from rest_framework.decorators import action
import django_filters
from django.db.models import Prefetch, Count
from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.decorators import action


# Initialize Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)
OTP_EXPIRY_TIME = 300  # 5 minutes in seconds

class ChatRoomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'

class ChatRoomFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    type = django_filters.CharFilter()
    
    class Meta:
        model = ChatRoom
        fields = ['name', 'type']

class ChatRoomListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = ChatRoomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = ChatRoomFilter
    search_fields = ['name', 'members__username']
    
    def get_serializer_class(self):
        return ChatRoomCreateSerializer if self.request.method == 'POST' else ChatRoomSerializer
    
    def get_queryset(self):
        return ChatRoom.objects.filter(
            members=self.request.user
        ).prefetch_related(
            Prefetch('memberships', queryset=Membership.objects.select_related('user')),
            Prefetch('messages', queryset=Message.objects.order_by('-timestamp')[:1], 
                    to_attr='prefetched_last_message')
        ).annotate(
            unread_count=Count('messages', 
                             filter=~Q(messages__read_by=self.request.user) & 
                             ~Q(messages__sender=self.request.user))
        ).order_by('-memberships__joined_at')


    @swagger_auto_schema(
        operation_description="Create a new chat room",
        request_body=ChatRoomCreateSerializer,
        responses={
            201: ChatRoomSerializer,
            400: "Bad Request"
        }
    )

    def create(self, request, *args, **kwargs):
        """Handle both group and direct chat creation"""
        if request.data.get('type') == 'direct':
            return self._create_direct_chat(request)
        return super().create(request, *args, **kwargs)
    
    def _create_direct_chat(self, request):
        """Special handling for direct chats"""
        other_user_id = request.data.get('members', [])
        if len(other_user_id) != 1:
            return Response(
                {"error": "Direct chats require exactly one other user"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            other_user = User.objects.get(id=other_user_id[0])
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check for existing direct chat
        existing_chat = ChatRoom.objects.filter(
            type='direct',
            members=request.user
        ).filter(
            members=other_user
        ).first()

        if existing_chat:
            return Response(
                ChatRoomSerializer(existing_chat, context={'request': request}).data,
                status=status.HTTP_200_OK
            )

        # Create new direct chat
        with transaction.atomic():
            chat = ChatRoom.objects.create(type='direct')
            Membership.objects.bulk_create([
                Membership(user=request.user, room=chat, role='admin'),
                Membership(user=other_user, room=chat, role='admin')
            ])

        return Response(
            ChatRoomSerializer(chat, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )

class ChatRoomDetailView(generics.RetrieveAPIView):
    """
    Retrieve details of a specific chat room.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatRoomSerializer
    
    def get_queryset(self):
        return ChatRoom.objects.filter(members=self.request.user)

def cache_messages(timeout=300):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(self, request, *args, **kwargs):
            cache_key = f'messages:{kwargs.get("room_id")}:{request.user.id}'
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                return Response(pickle.loads(cached_data))
            
            response = view_func(self, request, *args, **kwargs)
            
            if response.status_code == 200:
                redis_client.setex(cache_key, timeout, pickle.dumps(response.data))
            
            return response
        return wrapped_view
    return decorator

class MessageCursorPagination(CursorPagination):
    page_size = 50
    ordering = '-timestamp'
    cursor_query_param = 'before'

class MessageListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    pagination_class = MessageCursorPagination
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'message_create'

    
    def get_queryset(self):
        return Message.objects.filter(
            room_id=self.kwargs['room_id'],
            room__members=self.request.user,
            deleted_at__isnull=True
        ).select_related(
            'sender', 'room'
        ).order_by('-timestamp')


    def perform_create(self, serializer):
        room = get_object_or_404(
            ChatRoom.objects.filter(members=self.request.user),
            pk=self.kwargs['room_id']
        )
        
        message = serializer.save(
            sender=self.request.user,
            room=room,
            status='delivered'  # Assume immediate delivery
        )

        # Trigger real-time update (we'll implement this later)
        self._notify_new_message(message)

    def _notify_new_message(self, message):
        """Placeholder for WebSocket/Webhook integration"""
        pass

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        
        # Mark messages as read when fetched
        if response.data:
            Message.objects.filter(
                room_id=self.kwargs['room_id'],
                read_by=self.request.user
            ).exclude(
                read_by=self.request.user
            ).update(status='seen')
        
        return response

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

class MessageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsMessageOwner]
    serializer_class = MessageSerializer
    lookup_url_kwarg = 'message_id'

    def get_queryset(self):
        return Message.objects.filter(
            room__members=self.request.user,
            deleted_at__isnull=True
        )

    def perform_destroy(self, instance):
        """Soft delete by default"""
        instance.delete(soft_delete=True)

    def perform_update(self, serializer):
        """Prevent editing deleted messages"""
        if serializer.instance.deleted_at:
            raise PermissionDenied("Cannot edit deleted messages")
        serializer.save()

class MembershipViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MembershipSerializer

    def get_queryset(self):
        return Membership.objects.filter(
            room_id=self.kwargs['room_id'],
            room__members=self.request.user
        ).select_related('user', 'room')
    
    def create(self, request, *args, **kwargs):
        """Only admins can add members"""
        room = get_object_or_404(
            ChatRoom.objects.filter(members=request.user),
            pk=self.kwargs['room_id']
        )
        
        if not request.user.memberships.filter(
            room=room, 
            role='admin'
        ).exists():
            return Response(
                {"error": "Only admins can add members"},
                status=status.HTTP_403_FORBIDDEN
            )

        return super().create(request, *args, **kwargs)
    
    @action(detail=False, methods=['delete'])
    def remove_self(self, request, room_id):
        """Leave a chat room"""
        with transaction.atomic():
            membership = get_object_or_404(
                Membership.objects.select_for_update(),
                room_id=room_id,
                user=request.user
            )
            
            if membership.role == 'admin' and \
               Membership.objects.filter(
                   room_id=room_id, 
                   role='admin'
               ).count() <= 1:
                membership.room.delete()
                return Response(
                    {"detail": "Room deleted as you were the last admin"},
                    status=status.HTTP_200_OK
                )
            
            membership.delete()
            return Response(
                {"detail": "Successfully left the room"},
                status=status.HTTP_200_OK
            )

class UserSearchView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer  # Basic user serializer

    def get_queryset(self):
        search_term = self.request.query_params.get('q', '').strip()
        if not search_term:
            return User.objects.none()
        
        return User.objects.filter(
            Q(username__icontains=search_term) |
            Q(email__icontains=search_term)
        ).exclude(id=self.request.user.id)  # Exclude self

class DirectChatView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatRoomSerializer

    @swagger_auto_schema(
        operation_description="Create or retrieve a direct chat using user ID, username, or email",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='User ID'),
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='Email'),
            },
            required=[],
            example={"username": "john_doe"}
        ),
        responses={
            200: ChatRoomSerializer,
            201: ChatRoomSerializer,
            400: "Bad Request",
            404: "User not found"
        }
    )
    def post(self, request):
        # Get identifier from request (supports multiple ways)
        user_id = request.data.get('user_id')
        username = request.data.get('username')
        email = request.data.get('email')

        # Validate input
        identifiers = [i for i in [user_id, username, email] if i is not None]
        if len(identifiers) != 1:
            return Response(
                {"error": "Provide exactly one identifier (user_id, username, or email)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user
        try:
            if user_id:
                user = User.objects.get(id=user_id)
            elif username:
                user = User.objects.get(username__iexact=username)
            else:
                user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except User.MultipleObjectsReturned:
            return Response(
                {"error": "Multiple users found. Please use a more specific identifier"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prevent self-chat
        if user == request.user:
            return Response(
                {"error": "Cannot create direct chat with yourself"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for existing chat
        existing_chat = ChatRoom.objects.filter(
            type='direct',
            members=request.user
        ).filter(
            members=user
        ).first()

        if existing_chat:
            return Response(
                self.get_serializer(existing_chat).data,
                status=status.HTTP_200_OK
            )

        # Create new chat
        with transaction.atomic():
            chat_room = ChatRoom.objects.create(type='direct')
            Membership.objects.bulk_create([
                Membership(user=request.user, room=chat_room, role='admin'),
                Membership(user=user, room=chat_room, role='admin')
            ])

        return Response(
            self.get_serializer(chat_room).data,
            status=status.HTTP_201_CREATED
        )

class MarkMessagesReadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, room_id):
        messages = Message.objects.filter(
            room_id=room_id
        ).exclude(
            sender=request.user
        ).exclude(
            read_by=request.user
        )
        
        count = messages.count()
        for message in messages:
            message.read_by.add(request.user)
        
        return Response({
            'status': 'success',
            'messages_marked_read': count
        })
