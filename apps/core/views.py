from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from .models import User
from .serializers import UserSerializer, UserCreateSerializer
from .exceptions import APIResponse
from .permissions import IsAdmin


class UserViewSet(viewsets.GenericViewSet,
                  mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  mixins.CreateModelMixin):
    queryset = User.objects.all()
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return APIResponse(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return APIResponse(data=serializer.data, message='创建成功')

    @action(detail=False, methods=['get'], permission_classes=[])
    def me(self, request):
        if not request.user.is_authenticated:
            return APIResponse(message='未登录', code=401, status_code=401)
        serializer = UserSerializer(request.user)
        return APIResponse(data=serializer.data)
