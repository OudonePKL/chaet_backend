import pickle
from functools import wraps

from django.db import transaction
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, CharFilter

from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

import redis

from .models import ChatRoom, Message, Membership
from .serializers import (
    ChatRoomSerializer,
    ChatRoomCreateSerializer,
    MessageSerializer,
    MembershipSerializer,
)
from .permissions import IsMessageOwner
from users.models import User
from users.serializers import UserSerializer

# Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)
OTP_EXPIRY_TIME = 300


class ChatRoomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'


class ChatRoomFilter(FilterSet):
    name = CharFilter(lookup_expr='icontains')
    type = CharFilter()

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
            Prefetch('messages', queryset=Message.objects.order_by('-timestamp')[:1], to_attr='prefetched_last_message')
        ).annotate(
            unread_count=Count(
                'messages',
                filter=~Q(messages__read_by=self.request.user) & ~Q(messages__sender=self.request.user)
            )
        ).order_by('-memberships__joined_at')

    @swagger_auto_schema(
        operation_description="Create a new chat room",
        request_body=ChatRoomCreateSerializer,
        responses={201: ChatRoomSerializer, 400: "Bad Request"}
    )
    def create(self, request, *args, **kwargs):
        if request.data.get('type') == 'direct':
            return self._create_direct_chat(request)
        return super().create(request, *args, **kwargs)

    def _create_direct_chat(self, request):
        other_user_id = request.data.get('members', [])
        if len(other_user_id) != 1:
            return Response({"error": "Direct chats require exactly one other user"}, status=400)

        try:
            other_user = User.objects.get(id=other_user_id[0])
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        existing_chat = ChatRoom.objects.filter(
            type='direct', members=request.user
        ).filter(members=other_user).first()

        if existing_chat:
            return Response(ChatRoomSerializer(existing_chat, context={'request': request}).data, status=200)

        with transaction.atomic():
            chat = ChatRoom.objects.create(type='direct')
            Membership.objects.bulk_create([
                Membership(user=request.user, room=chat, role='admin'),
                Membership(user=other_user, room=chat, role='admin')
            ])

        return Response(ChatRoomSerializer(chat, context={'request': request}).data, status=201)


class ChatRoomDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
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
        ).select_related('sender', 'room').order_by('-timestamp')

    def perform_create(self, serializer):
        room = get_object_or_404(ChatRoom.objects.filter(members=self.request.user), pk=self.kwargs['room_id'])
        message = serializer.save(sender=self.request.user, room=room, status='delivered')
        self._notify_new_message(message)

    def _notify_new_message(self, message):
        pass  # Placeholder for real-time

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if response.data:
            Message.objects.filter(
                room_id=self.kwargs['room_id'],
                read_by=self.request.user
            ).exclude(read_by=self.request.user).update(status='seen')
        return response

    @swagger_auto_schema(
        operation_description="Create a new message",
        request_body=MessageSerializer,
        responses={201: MessageSerializer, 400: "Bad Request", 403: "Forbidden"}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


class MessageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsMessageOwner]
    serializer_class = MessageSerializer
    lookup_url_kwarg = 'message_id'

    def get_queryset(self):
        return Message.objects.filter(room__members=self.request.user, deleted_at__isnull=True)

    def perform_destroy(self, instance):
        instance.delete(soft_delete=True)

    def perform_update(self, serializer):
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
        room = get_object_or_404(ChatRoom.objects.filter(members=request.user), pk=self.kwargs['room_id'])

        if not request.user.memberships.filter(room=room, role='admin').exists():
            return Response({"error": "Only admins can add members"}, status=403)

        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['delete'])
    def remove_self(self, request, room_id):
        with transaction.atomic():
            membership = get_object_or_404(
                Membership.objects.select_for_update(),
                room_id=room_id,
                user=request.user
            )

            if membership.role == 'admin' and \
               Membership.objects.filter(room_id=room_id, role='admin').count() <= 1:
                membership.room.delete()
                return Response({"detail": "Room deleted as you were the last admin"}, status=200)

            membership.delete()
            return Response({"detail": "Successfully left the room"}, status=200)


class UserSearchView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        if not query:
            return User.objects.none()
        return User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        ).exclude(id=self.request.user.id)


class DirectChatView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChatRoomSerializer

    @swagger_auto_schema(
        operation_description="Create or retrieve direct chat",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=[],
            example={"username": "john_doe"}
        ),
        responses={200: ChatRoomSerializer, 201: ChatRoomSerializer, 400: "Bad Request", 404: "User not found"}
    )
    def post(self, request):
        user_id = request.data.get('user_id')
        username = request.data.get('username')
        email = request.data.get('email')

        identifiers = [i for i in [user_id, username, email] if i]
        if len(identifiers) != 1:
            return Response({"error": "Provide exactly one identifier"}, status=400)

        try:
            if user_id:
                user = User.objects.get(id=user_id)
            elif username:
                user = User.objects.get(username__iexact=username)
            else:
                user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
        except User.MultipleObjectsReturned:
            return Response({"error": "Multiple users found"}, status=400)

        if user == request.user:
            return Response({"error": "Cannot chat with yourself"}, status=400)

        existing_chat = ChatRoom.objects.filter(type='direct', members=request.user).filter(members=user).first()
        if existing_chat:
            return Response(self.get_serializer(existing_chat).data, status=200)

        with transaction.atomic():
            chat = ChatRoom.objects.create(type='direct')
            Membership.objects.bulk_create([
                Membership(user=request.user, room=chat, role='admin'),
                Membership(user=user, room=chat, role='admin')
            ])

        return Response(self.get_serializer(chat).data, status=201)


class MarkMessagesReadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, room_id):
        messages = Message.objects.filter(
            room_id=room_id
        ).exclude(sender=request.user).exclude(read_by=request.user)

        count = messages.count()
        for message in messages:
            message.read_by.add(request.user)

        return Response({'status': 'success', 'messages_marked_read': count})
