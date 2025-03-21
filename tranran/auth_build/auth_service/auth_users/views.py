# Create your views here.

from .models import User, Friends
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, ListAPIView, UpdateAPIView
from .serializers import (
    UserDetailSerializer,
    UpdateUserSerializer,
    UpdatePasswordSerializer)
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .permissions import IsSameUser
from rest_framework.request import Request
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework import serializers
from .utils import _AuthCache
from core.asgi import publishers
from asgiref.sync import async_to_sync


class UpdateUserInfo(UpdateAPIView):
    serializer_class = UpdateUserSerializer
    queryset = User.objects.all()
    lookup_field = 'username'
    http_method_names = ['patch']
    permission_classes = [IsSameUser]
    
    def patch(self, request, *agrs, **kwargs):
        if not request.data:
            return Response({"detail" : "empty request data"},
                            status.HTTP_400_BAD_REQUEST)
        partial = True
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        # check additional fields in the request data
        for key in request.data.keys():
            if key not in serializer.get_fields():
                return Response({"detail" : "ivalid key provided"},
                    status=status.HTTP_400_BAD_REQUEST)
        # check serializer validation and perform the update
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        # just copied it from original function, ignore it 
        ###################
        if getattr(instance, '_prefetched_objects_cache', None):
             # If 'prefetch_related' has been applied to a queryset, we need to
             # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
        ###################
        response = {
            "detail" : "update successful",
            "updated_fields" : request.data.keys()
        }
        return Response(response)


class UpdatePassword(UpdateAPIView):
    permission_classes = [IsSameUser]
    queryset = User.objects.all()
    lookup_field = 'username'
    http_method_names = ['patch']
    serializer_class = UpdatePasswordSerializer
    
    def patch(self, request, *args, **kwargs):
        if not request.data:
            return Response({"detail" : "empty request data"},
                            status.HTTP_400_BAD_REQUEST)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer=serializer)
        return Response(status=status.HTTP_202_ACCEPTED,
                        data={"detail" : "Sucessfully updated the password"})
        

class GetUser(RetrieveAPIView):
    serializer_class = UserDetailSerializer
    queryset = User.objects.all()
    lookup_field = 'username'
    permission_classes = [IsAuthenticated]

class GetMyInfo(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, *args, **kwargs):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)

from .serializers import AuthProviderSerializer



class ListUsers(ListAPIView):
    serializer_class = UserDetailSerializer
    queryset = User.objects.all()
    authentication_classes = []

class GetFriends(APIView):
    class FriendsSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields =  ['id', 'username', 'email', 'icon_url']


    permission_classes = [IsAuthenticated]
    
    def get(self, request : Request, *args, **kwargs):
        user : User = request.user
        friends = Friends.objects.get_friends(user)
        objects = User.objects.filter(id__in=friends)
        ser = self.FriendsSerializer(objects, many=True)
        return Response(data=ser.data)

class SendFriendRequest(APIView):
    permission_classes = [IsAuthenticated]

    notif = publishers[1]
    
    
    def get(self, request :Request, *args, **kwargs):
        user : User = request.user
        requested_username = kwargs.get("username")
        try:
            to_user : User = get_object_or_404(User, username=requested_username)
            Friends.objects.add_friend(from_user=user, to_user=to_user)
            data = {
                'type' : "send_notification",
                'data' : {
                    'user_id' : str(to_user.id),
                    'message' : f'you received a friend request from {user.username}'
                }
            }
            async_to_sync(self.notif.publish)(data)
            return Response(data={"detail" : "Friend Request sent"})
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"detail" : "User Not Found"})
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"detail": str(e)})

class CheckReceivedFriend(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, *args, **kwargs):
        current_user = request.user
        data = Friends.objects.get_received_reqs(current_user)
        return Response(data)


class CheckSentFriend(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request : Request, *args, **kwargs):
        current_user = request.user
        sent_requests = Friends.objects.get_sent_reqs(current_user)
        # data = [req.to_user.username for req in sent_requests]
        return Response(sent_requests)

class ChangeFriend(APIView):

    permission_classes = [IsAuthenticated]

    actions = {}

    def __init__(self, **kwargs):
        self.actions = {
            'accept' : self.accept,
            'reject' : self.reject,
            'unfriend' : self.unfriend,
            'block' : self.block,
        }
        super().__init__(**kwargs)
    class ChangeSerializer(serializers.Serializer):
        
        change = serializers.CharField(max_length=10, required=True)

        def validate_change(self, value):
            choices = ['accept', 'reject', 'unfriend', 'block']
            if value not in choices:
                raise serializers.ValidationError("invalid relation change value")
            return value
    
    def get_relation(self, user, other):
        try:
            relation = self.filter(from_user=user, to_user=other).get()
            return relation
        except Friends.DoesNotExist:
            try:
                relation = self.filter(from_user=other, to_user=user).get()
                return relation
            except Friends.DoesNotExist:
                return None

    def accept(self, user : User, other : User):
        try:
            relation : Friends = Friends.objects.filter(from_user=other, to_user=user).all()
            if relation.status != "pending":
                raise Exception(f"Your current relation is : {relation.status}")
            relation.status = "accepted"
            relation.save()
            return "Success"
        except Friends.DoesNotExist:
            raise Exception("You didn't receive any friend request from this user.")
    def reject(self, user : User, other : User):
        try:
            relation : Friends = Friends.objects.filter(from_user=other, to_user=user).all()
            if relation.status != "pending":
                raise Exception(f"Your current relation is : {relation.status}")
            relation.delete()
            return "Success"
        except Friends.DoesNotExist:
            raise Exception("You didn't receive any friend request from this user.")

    def unfriend(self, user : User, other : User):
       
        relation : Friends = self.get_relation(user, other)
        if not relation:
            raise Exception("You are not even friends.")
        relation.delete()
        return "Success"
        
    def block(self, user : User, other : User):
        
        relation : Friends = self.get_relation(user, other)
        if relation:
            if relation.status == "blocked":
                return "User already blocked you hehe"
            relation.status = "blocked"
            relation.save()
            return "Success"
        relation = Friends.objects.create(from_user=user, to_user=other, status="blocked")
        relation.save()
        return "Success"
    
    def unblock(self, user : User, other : User):
        relation : Friends = self.get_relation(user, other)
        if not relation:
            raise Exception("You are not even friends or blocking each other")
        relation.status = "accepted"
        relation.save()
        return "Success"

    def post(self, request : Request, *args, **kwargs):
        try:
            user : User = request.user
            serializer = self.ChangeSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            change = serializer.data["change"]
            res = self.actions[change](user)
            return Response(status=status.HTTP_201_CREATED, data={"detail" : res})
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"detail" : str(e)})


class BanSelf(APIView):
    permission_classes = [IsAuthenticated]
    cache = _AuthCache

    def get(self, request: Request, *args, **kwargs):
        current_user: User = request.user
        if current_user.is_active:
            print("current user: ", current_user.username)
            self.cache.BlacklistUserToken(current_user.username)
            self.cache.remove_access_session(current_user.id)
            current_user.is_active = False
            current_user.save()
            return Response(data={"detail" : "You are now banned!"})
        return Response(data={"detail" : "You are already banned."})

import json
from django.core.mail import send_mail
import pyotp

class ResetPassword(APIView):
    authentication_classes = []
    cache = _AuthCache

    class CodeRequest(serializers.Serializer):
        email = serializers.EmailField(required=True)

    def post(self, request : Request, *args, **kwargs):
        ser = self.CodeRequest(data=request.data)
        ser.is_valid(raise_exception=True) # will return 400 if fails
        email = ser.data["email"]
        try:
            user = get_object_or_404(User, email=email)
            if not user.is_active:
                return Response(status=status.HTTP_400_BAD_REQUEST,
                                data={"detail" : "This Account has been permanently banned."})
            code = self.cache.reset_code_action(email=user.email,action='set')
            send_mail(
                from_email=None,
                subject="Password Reset",
                message=f"Your password reset code is {code}",
                recipient_list=[user.email],
                fail_silently=False
            )
            return Response(status=status.HTTP_202_ACCEPTED, data={"detail": "A code has been sent to your email."})
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND,
                            data={"detail" : "User Not Found"})
        except  json.JSONDecodeError as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"detail" : "Internal Server Error"})            
        except Exception as e:
            print(f"Error in Password Reset : {e}")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"detail" : "Internal Server Error"})

from .models import AuthProvider

class PasswordVerify(APIView):
    authentication_classes = []
    cache = _AuthCache

    class Code(serializers.Serializer):
        code = serializers.IntegerField(required=True)
        email = serializers.EmailField(required=True)

    def post(self, request: Request, *args, **kwargs):
        ser = self.Code(data=request.data)
        ser.is_valid(raise_exception=True)   
        email = ser.data["email"]
        code = ser.data["code"]     
        cache_code = self.cache.reset_code_action(action="get", email=email)
        if cache_code is None:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={"detail" : "User with this email did not request any code"})
        if int(cache_code) != code:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={"detail" : "Invalid code"})
        try:
            user = get_object_or_404(User, email=email)
            self.cache.reset_code_action(email=email, action='delete')
            new_password = pyotp.random_base32()
            obj, created = AuthProvider.objects.get_or_create(name="Email")
            user.auth_provider.add(obj)
            if user.two_factor_enabled:
                user.two_factor_enabled = False
                user.two_factor_secret = ""
            self.cache.BlacklistUserToken(user.username)
            self.cache.delete_access_session(user.id)
            user.set_password(new_password)
            user.save()
            send_mail(
                from_email=None,
                subject="Your password has been reset",
                message=f"Your new password is {new_password}",
                recipient_list=[email],
                fail_silently=False
            )
            return Response(data={"detail" : "A new Password has been sent to your email"})
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND,
                            data={"detail" : "User Not Found"})
        except Exception as e:
            print(f"Error in Password Verify : {e}")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"detail" : "Internal Server Error"})
        
from .permissions import isNginx

class CDNVerify(APIView):
    authentication_classes = []
    permission_classes = [isNginx]

    def get(self, request, *args , **kwargs):
        return Response(data={"detail" : "works!"})
    
class Upload(APIView):

    class imageSerial(serializers.Serializer):
        image = serializers.ImageField()


class sendNotif(APIView):
    permission_classes = [IsAuthenticated]
    notif = publishers[1]

    @async_to_sync
    async def get(self, request : Request, *args, **kwargs):
        try:
            user : User = request.user
            data = {
                'type' : "send_notification",
                'data' : {
                    'user_id' : str(user.id),
                    'message' : 'Test message'
                }
            }
            await self.notif.publish(data)
            return Response(data={"detail" : "published successuly"})
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"detail" : f"error publishing, {e}"})
