from rest_framework import serializers
from .models import ChatRoom, Message, Membership, Reaction
from users.serializers import UserSerializer


class ChatRoomSerializer(serializers.ModelSerializer):
    members = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ['id', 'name', 'type', 'members', 'created_at', 'last_message', 'unread_count']
        read_only_fields = ['created_at']

    def get_unread_count(self, obj):
        user = self.context['request'].user
        return obj.messages.exclude(sender=user).exclude(read_by=user).count()

    def get_last_message(self, obj):
        last_message = obj.messages.order_by('-timestamp').first()
        if last_message:
            return MessageSerializer(last_message).data
        return None

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

    class Meta:
        model = Message
        fields = ['id', 'room', 'sender', 'content', 'timestamp', 'attachment', 'attachment_url', 'attachment_type']
        read_only_fields = ['timestamp']

    def get_attachment_url(self, obj):
        if obj.attachment:
            return self.context['request'].build_absolute_uri(obj.attachment.url)
        return None

class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'room', 'user', 'user_id', 'role', 'joined_at']
        read_only_fields = ['joined_at', 'room'] 

class ReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reaction
        fields = ['id', 'message', 'user', 'emoji', 'created_at']
        read_only_fields = ['user', 'created_at']

