from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChatRoomListCreateView,
    ChatRoomDetailView,
    MessageListView,
    MessageDetailView,
    MembershipViewSet,
    UserSearchView,
    DirectChatView,
    MarkMessagesReadView,
)

router = DefaultRouter()
router.register(r'chatrooms/(?P<room_id>\d+)/memberships', MembershipViewSet, basename='membership')

urlpatterns = [
    # Chat rooms
    path('chatrooms/', ChatRoomListCreateView.as_view(), name='chatroom-list-create'),
    path('chatrooms/<int:pk>/', ChatRoomDetailView.as_view(), name='chatroom-detail'),

    # Messages
    path('chatrooms/<int:room_id>/messages/', MessageListView.as_view(), name='message-list-create'),
    path('chatrooms/<int:room_id>/messages/<int:message_id>/', MessageDetailView.as_view(), name='message-detail'),

    # Memberships (using viewset router)
    path('', include(router.urls)),

    # User search
    path('users/search/', UserSearchView.as_view(), name='user-search'),

    # Direct chat creation/retrieval
    path('chatrooms/direct/', DirectChatView.as_view(), name='direct-chat'),

    # Mark messages as read
    path('chatrooms/<int:room_id>/mark-read/', MarkMessagesReadView.as_view(), name='mark-messages-read'),
]
