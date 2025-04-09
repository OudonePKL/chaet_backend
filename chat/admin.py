from django.contrib import admin
from .models import ChatRoom, Message, Membership

admin.site.register(ChatRoom)
admin.site.register(Message)
admin.site.register(Membership)
