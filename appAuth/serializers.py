# serializers.py
from rest_framework import serializers
from home.models import User
from django.contrib.auth import get_user_model



class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'phone_number', 'role', 'first_name', 'last_name')
        read_only_fields = ('id', 'role')