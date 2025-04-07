from rest_framework import serializers
from .models import ChatRoom, Message, Membership, Reaction
from django.db import models, IntegrityError
from users.serializers import UserSerializer


class ChatRoomSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()  # Custom handling
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    my_membership = serializers.SerializerMethodField()  # New field

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'name', 'type', 'members', 'created_at',
            'last_message', 'unread_count', 'my_membership'
        ]
        read_only_fields = ['created_at']

    def get_members(self, obj):
        """Optimized member serialization with prefetch_related"""
        memberships = obj.memberships.select_related('user').all()
        return [
            {
                'id': m.user.id,
                'username': m.user.username,
                'role': m.role,
                'joined_at': m.joined_at
            } 
            for m in memberships
        ]

    def get_my_membership(self, obj):
        """Show current user's role in the chat"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        
        membership = obj.memberships.filter(user=request.user).first()
        if membership:
            return {
                'role': membership.role,
                'joined_at': membership.joined_at,
                'can_invite': membership.role == 'admin'
            }
        return None

    def get_last_message(self, obj):
        """Use prefetched data if available"""
        last_message = getattr(obj, 'prefetched_last_message', None)
        if not last_message:
            last_message = obj.messages.order_by('-timestamp').first()
        
        if last_message:
            return {
                'id': last_message.id,
                'content': last_message.content,
                'timestamp': last_message.timestamp,
                'sender_id': last_message.sender.id
            }
        return None

    def get_unread_count(self, obj):
        user = self.context['request'].user
        return obj.messages.exclude(
            sender=user
        ).exclude(
            read_by=user
        ).count()

class ChatRoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoom
        fields = ['name', 'type', 'members']

    def validate(self, data):
        if data.get('type') == 'group' and not data.get('name'):
            raise serializers.ValidationError("Group chat must have a name")
        if data.get('type') == 'group' and data.get('name'):
            # Check if a group with this name already exists
            if ChatRoom.objects.filter(name=data['name'], type='group').exists():
                raise serializers.ValidationError("A group with this name already exists")
        
        # Ensure at least one member is added
        members_data = self.initial_data.get('members', [])
        if not members_data or len(members_data) < 1:
            raise serializers.ValidationError("A group chat must have at least one other user.")

        return data

    def create(self, validated_data):
        members_data = self.initial_data.get('members', [])
        request_user = self.context['request'].user
        # Ensure at least one member is added besides the creator
        if not members_data or request_user.id in members_data:
            raise serializers.ValidationError("You must add at least one other user.")

        chat_room = ChatRoom.objects.create(**validated_data)

        # Add the creator as an admin
        Membership.objects.create(user=request_user, room=chat_room, role='admin')

        # Add other members
        for user_id in members_data:
            Membership.objects.create(user_id=user_id, room=chat_room, role='member')

        return chat_room

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    attachment_url = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()  # New field
    is_deleted = serializers.SerializerMethodField()  # New field

    class Meta:
        model = Message
        fields = [
            'id', 'room', 'sender', 'content', 'timestamp',
            'attachment_url', 'attachment_type', 'reactions',
            'status', 'is_deleted'
        ]
        read_only_fields = ['timestamp', 'sender']

    def get_attachment_url(self, obj):
        if obj.attachment:
            request = self.context.get('request')
            url = obj.attachment.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None

    def get_reactions(self, obj):
        """Return emoji counts like {'👍': 3, '❤️': 1}"""
        return obj.reactions.values('emoji').annotate(
            count=models.Count('emoji')
        ).order_by('-count')

    def get_is_deleted(self, obj):
        return obj.deleted_at is not None

    def to_representation(self, instance):
        """Hide content if message is deleted"""
        data = super().to_representation(instance)
        if instance.deleted_at:
            data['content'] = "[This message was deleted]"
            data['attachment_url'] = None
        return data

class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    can_edit = serializers.SerializerMethodField()  # New field

    class Meta:
        model = Membership
        fields = [
            'id', 'room', 'user', 'user_id', 'role',
            'joined_at', 'last_role_change', 'can_edit'
        ]
        read_only_fields = ['joined_at', 'room']

    def get_can_edit(self, obj):
        """Only admins can modify roles"""
        request = self.context.get('request')
        if not request:
            return False
        return obj.room.memberships.filter(
            user=request.user,
            role='admin'
        ).exists()

    def validate(self, data):
        """Prevent non-admins from assigning admin role"""
        request = self.context.get('request')
        if 'role' in data and data['role'] == 'admin':
            if not request or not request.user.is_authenticated:
                raise serializers.ValidationError("Authentication required")
            
            is_admin = Membership.objects.filter(
                room=data.get('room'),
                user=request.user,
                role='admin'
            ).exists()
            
            if not is_admin:
                raise serializers.ValidationError("Only admins can assign admin role")
        
        return data

class ReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reaction
        fields = ['id', 'emoji', 'created_at']  # Removed message/user as they're auto-set
        read_only_fields = ['created_at']

    def create(self, validated_data):
        return Reaction.objects.create(
            message=self.context['message'],
            user=self.context['request'].user,
            **validated_data
        )

