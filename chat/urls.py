from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChatRoomListCreateView,
    ChatRoomDetailView,
    MessageListView,
    MessageDetailView,
    MembershipViewSet,
    DirectChatView,
    MarkMessagesReadView,
    ReactionViewSet
)

router = DefaultRouter()
router.register(r'rooms/(?P<room_id>\d+)/members', MembershipViewSet, basename='membership')
router.register(r'messages/(?P<message_id>\d+)/reactions', ReactionViewSet, basename='reaction')

urlpatterns = [
    # Chat Rooms
    path('rooms/', ChatRoomListCreateView.as_view(), name='room-list-create'),
    path('rooms/<int:pk>/', ChatRoomDetailView.as_view(), name='room-detail'),
    
    # Messages
    path('rooms/<int:room_id>/messages/', MessageListView.as_view(), name='message-list'),
    path('rooms/<int:room_id>/messages/<int:message_id>/', MessageDetailView.as_view(), name='message-detail'),
    path('rooms/<int:room_id>/mark-read/', MarkMessagesReadView.as_view(), name='mark-read'),
    
    # Direct Chat
    path('direct-chat/', DirectChatView.as_view(), name='direct-chat-create'),
    
    # Membership Management
    path('rooms/<int:room_id>/members/remove-self/', 
         MembershipViewSet.as_view({'delete': 'remove_self'}), 
         name='membership-remove-self'),
    path('rooms/<int:room_id>/members/<int:user_id>/remove/', 
         MembershipViewSet.as_view({'delete': 'remove_member'}), 
         name='membership-remove-member'),
    
    # Include router URLs last
    path('', include(router.urls)),
]