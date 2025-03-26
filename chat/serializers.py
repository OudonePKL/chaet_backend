from rest_framework import serializers
from .models import ChatRoom, Message, Membership
from users.serializers import UserSerializer

class ChatRoomSerializer(serializers.ModelSerializer):
    members = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ['id', 'name', 'type', 'members', 'created_at', 'last_message']
        read_only_fields = ['created_at']

    def get_last_message(self, obj):
        last_message = obj.messages.order_by('-timestamp').first()
        if last_message:
            return MessageSerializer(last_message).data
        return None

class ChatRoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoom
        fields = ['name', 'type', 'members']
        extra_kwargs = {
            'members': {'required': False}
        }

    def validate(self, data):
        if data.get('type') == 'group' and not data.get('name'):
            raise serializers.ValidationError("Group chat must have a name")
        if data.get('type') == 'group' and data.get('name'):
            # Check if a group with this name already exists
            if ChatRoom.objects.filter(name=data['name'], type='group').exists():
                raise serializers.ValidationError("A group with this name already exists")
        return data

    def create(self, validated_data):
        members_data = validated_data.pop('members', [])
        chat_room = ChatRoom.objects.create(**validated_data)
        
        # Add the creator as an admin
        Membership.objects.create(
            user=self.context['request'].user,
            room=chat_room,
            role='admin'
        )
        
        # Add other members if provided
        for user_id in members_data:
            Membership.objects.create(
                user_id=user_id,
                room=chat_room,
                role='member'
            )
        
        return chat_room

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'room', 'sender', 'content', 'timestamp']
        read_only_fields = ['timestamp']

class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'room', 'user', 'user_id', 'role', 'joined_at']
        read_only_fields = ['joined_at', 'room'] 