from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChatRoomListCreateView,
    ChatRoomDetailView,
    MessageListView,
    MembershipViewSet,
    DirectChatView,
)

router = DefaultRouter()
router.register(r'rooms/(?P<room_id>\d+)/members', MembershipViewSet, basename='membership')

urlpatterns = [
    # Chat Rooms
    path('rooms/', ChatRoomListCreateView.as_view(), name='room-list-create'),
    path('rooms/<int:pk>/', ChatRoomDetailView.as_view(), name='room-detail'),
    path('rooms/search/', ChatRoomListCreateView.as_view(), name='room-search'),
    
    # Messages
    path('rooms/<int:room_id>/messages/', MessageListView.as_view(), name='message-list-create'),

    # Direct Chat
    path('direct-chat/<int:user_id>/', DirectChatView.as_view(), name='direct-chat'),

    # Members (ViewSet actions)
    path('rooms/<int:room_id>/members/remove-self/', MembershipViewSet.as_view({'delete': 'remove_self'}), name='membership-remove-self'),
    path('rooms/<int:room_id>/members/<int:user_id>/remove/', MembershipViewSet.as_view({'delete': 'remove_member'}), name='membership-remove-member'),

    # Include router URLs last
    path('', include(router.urls)),
]
