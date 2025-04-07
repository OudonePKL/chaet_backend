from django.contrib import admin
from .models import ChatRoom, Message, Membership, Reaction

admin.site.register(ChatRoom)
admin.site.register(Message)
admin.site.register(Membership)
admin.site.register(Reaction)
