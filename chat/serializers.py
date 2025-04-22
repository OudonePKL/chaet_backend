from rest_framework import serializers
from .models import ChatRoom, Message, Membership
from users.serializers import UserSerializer
from users.models import User

class ChatRoomSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    my_membership = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'name', 'type', 'members', 'created_at',
            'last_message', 'unread_count', 'my_membership'
        ]
        read_only_fields = ['created_at']

    def get_members(self, obj: ChatRoom):
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

    def get_my_membership(self, obj: ChatRoom):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        
        membership = obj.memberships.filter(user=user).first()
        if membership:
            return {
                'role': membership.role,
                'joined_at': membership.joined_at,
                'can_invite': membership.role == 'admin'
            }
        return None

    def get_last_message(self, obj):
        last_message = Message.objects.filter(room=obj).order_by('-timestamp').first()
        if last_message:
            return {
                'id': last_message.id,
                'text': last_message.content,
                'timestamp': last_message.timestamp,
                'sender': last_message.sender.username
            }
        return None

    def get_unread_count(self, obj: ChatRoom):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return 0
        return obj.messages.exclude(sender=user).exclude(read_by=user).count()

class ChatRoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoom
        fields = ['name', 'type', 'members']

    def validate(self, data):
        chat_type = data.get('type')
        name = data.get('name')

        if chat_type == 'group':
            if not name:
                raise serializers.ValidationError("Group chat must have a name.")
            if ChatRoom.objects.filter(name=name, type='group').exists():
                raise serializers.ValidationError("A group with this name already exists.")

        members = self.initial_data.get('members', [])
        if not members or len(members) < 1:
            raise serializers.ValidationError("At least one member must be added.")

        return data

    def create(self, validated_data):
        members_data = self.initial_data.get('members', [])
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        if not members_data or user.id in members_data:
            raise serializers.ValidationError("You must add at least one other user.")

        chat_room = ChatRoom.objects.create(**validated_data)

        # Add creator as admin
        Membership.objects.create(user=user, room=chat_room, role='admin')

        # Add others
        for user_id in members_data:
            Membership.objects.create(user_id=user_id, room=chat_room, role='member')

        return chat_room

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    attachment_url = serializers.SerializerMethodField()
    is_deleted = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'room', 'sender', 'content', 'timestamp',
            'attachment_url', 'attachment_type',
            'status', 'is_deleted'
        ]
        read_only_fields = ['timestamp', 'sender']

    def get_attachment_url(self, obj: Message):
        if not obj.attachment:
            return None
        request = self.context.get('request')
        url = obj.attachment.url
        return request.build_absolute_uri(url) if request else url

    def get_is_deleted(self, obj: Message):
        return obj.is_deleted()

    def to_representation(self, instance: Message):
        data = super().to_representation(instance)
        if instance.is_deleted():
            data['content'] = "[This message was deleted]"
            data['attachment_url'] = None
        return data


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'room']
        extra_kwargs = {
            'room': {'read_only': True}
        }

    def create(self, validated_data):
        validated_data['room_id'] = self.context['view'].kwargs['room_id']
        return super().create(validated_data)

    def validate(self, data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if data.get('role') == 'admin':
            if not user or not user.is_authenticated:
                raise serializers.ValidationError("Authentication required to assign admin role.")
            
            if not Membership.objects.filter(room=data.get('room'), user=user, role='admin').exists():
                raise serializers.ValidationError("Only admins can assign the admin role.")

        return data


class MembershipWriteSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    
    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'room']
        extra_kwargs = {
            'room': {'read_only': True}
        }

class MembershipReadSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Membership
        fields = ['id', 'user', 'role', 'room']
        extra_kwargs = {
            'room': {'read_only': True}
        }