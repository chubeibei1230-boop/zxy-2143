from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import ServiceType, ServiceSite, ServiceItem, ServiceStatus, OperationType
from .serializers import (
    ServiceTypeSerializer, ServiceSiteSerializer,
    ServiceItemListSerializer, ServiceItemDetailSerializer, ServiceItemCreateSerializer,
    StatusTransitionSerializer, FieldUpdateSerializer, UndoRedoSerializer, AuditLogSerializer,
)
from .services import (
    ServiceItemStateMachine, create_service_item, generate_item_no,
    StateMachineError, PermissionDeniedError, InvalidTransitionError,
)
from apps.core.exceptions import APIResponse
from apps.core.permissions import IsAdmin, IsAdminOrOperatorA, IsAdminOrOperatorB


class ServiceTypeViewSet(viewsets.ModelViewSet):
    queryset = ServiceType.objects.all()
    serializer_class = ServiceTypeSerializer
    permission_classes = [IsAdmin]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if not request.user.is_admin:
            queryset = queryset.filter(is_active=True)
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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return APIResponse(data=serializer.data, message='更新成功')

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return APIResponse(message='已禁用')


class ServiceSiteViewSet(viewsets.ModelViewSet):
    queryset = ServiceSite.objects.all()
    serializer_class = ServiceSiteSerializer
    permission_classes = [IsAdmin]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if not request.user.is_admin:
            queryset = queryset.filter(is_active=True)
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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return APIResponse(data=serializer.data, message='更新成功')

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return APIResponse(message='已禁用')


class ServiceItemViewSet(viewsets.GenericViewSet,
                         mixins.ListModelMixin,
                         mixins.RetrieveModelMixin):
    queryset = ServiceItem.objects.select_related(
        'service_type', 'site', 'creator', 'assignee', 'reviewer'
    ).all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ServiceItemCreateSerializer
        if self.action == 'list':
            return ServiceItemListSerializer
        return ServiceItemDetailSerializer

    def get_queryset(self):
        from apps.core.models import Role
        from .models import ServiceStatus
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_admin:
            if user.is_operator_b:
                qs = qs.filter(
                    Q(creator=user) | Q(assignee=user) | Q(reviewer=user) |
                    Q(status=ServiceStatus.PENDING_REVIEW)
                )
            else:
                qs = qs.filter(
                    Q(creator=user) | Q(assignee=user) | Q(reviewer=user)
                )
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        keyword = self.request.query_params.get('keyword')
        if keyword:
            qs = qs.filter(
                Q(title__icontains=keyword) |
                Q(applicant_name__icontains=keyword) |
                Q(item_no__icontains=keyword)
            )
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return APIResponse(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse(data=serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrOperatorA])
    def submit(self, request):
        serializer = ServiceItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data.copy()
        data['item_no'] = generate_item_no()
        item = create_service_item(data, request.user)
        result_serializer = ServiceItemDetailSerializer(item)
        return APIResponse(data=result_serializer.data, message='提交成功', code=0, status_code=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        service_item = self.get_object()
        serializer = StatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sm = ServiceItemStateMachine(service_item, request.user)
        try:
            item = sm.transition_to(
                target_status=data['target_status'],
                note=data.get('note', ''),
                assignee_id=data.get('assignee_id'),
                handler_note=data.get('handler_note'),
                review_note=data.get('review_note'),
                cancel_reason=data.get('cancel_reason'),
            )
        except InvalidTransitionError as e:
            return APIResponse(message=str(e), code=400, status_code=status.HTTP_400_BAD_REQUEST)
        except PermissionDeniedError as e:
            return APIResponse(message=str(e), code=403, status_code=status.HTTP_403_FORBIDDEN)
        except StateMachineError as e:
            return APIResponse(message=str(e), code=400, status_code=status.HTTP_400_BAD_REQUEST)

        result_serializer = ServiceItemDetailSerializer(item)
        return APIResponse(data=result_serializer.data, message='状态更新成功')

    @action(detail=True, methods=['post'])
    def update_fields(self, request, pk=None):
        service_item = self.get_object()
        serializer = FieldUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        note = data.pop('note', '')

        updates = {}
        operation_type = None

        if 'assignee_id' in data:
            updates['assignee_id'] = data['assignee_id']
            operation_type = OperationType.ASSIGNEE_CHANGE
        if 'handler_note' in data:
            updates['handler_note'] = data['handler_note']
            operation_type = OperationType.HANDLER_NOTE_CHANGE
        if 'appointment_time' in data:
            updates['appointment_time'] = data['appointment_time']
            operation_type = OperationType.APPOINTMENT_CHANGE

        if not updates or not operation_type:
            return APIResponse(message='未提供有效更新字段', code=400, status_code=status.HTTP_400_BAD_REQUEST)

        sm = ServiceItemStateMachine(service_item, request.user)
        try:
            item = sm.update_fields(operation_type, note=note, **updates)
        except StateMachineError as e:
            return APIResponse(message=str(e), code=400, status_code=status.HTTP_400_BAD_REQUEST)

        result_serializer = ServiceItemDetailSerializer(item)
        return APIResponse(data=result_serializer.data, message='更新成功')

    @action(detail=True, methods=['post'])
    def undo(self, request, pk=None):
        service_item = self.get_object()
        serializer = UndoRedoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sm = ServiceItemStateMachine(service_item, request.user)
        try:
            item = sm.undo(data['audit_log_id'])
        except (InvalidTransitionError, StateMachineError) as e:
            return APIResponse(message=str(e), code=400, status_code=status.HTTP_400_BAD_REQUEST)
        except PermissionDeniedError as e:
            return APIResponse(message=str(e), code=403, status_code=status.HTTP_403_FORBIDDEN)

        result_serializer = ServiceItemDetailSerializer(item)
        return APIResponse(data=result_serializer.data, message='撤销成功')

    @action(detail=True, methods=['post'])
    def redo(self, request, pk=None):
        service_item = self.get_object()
        serializer = UndoRedoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sm = ServiceItemStateMachine(service_item, request.user)
        try:
            item = sm.redo(data['audit_log_id'])
        except (InvalidTransitionError, StateMachineError) as e:
            return APIResponse(message=str(e), code=400, status_code=status.HTTP_400_BAD_REQUEST)
        except PermissionDeniedError as e:
            return APIResponse(message=str(e), code=403, status_code=status.HTTP_403_FORBIDDEN)

        result_serializer = ServiceItemDetailSerializer(item)
        return APIResponse(data=result_serializer.data, message='重做成功')

    @action(detail=True, methods=['get'])
    def audit_logs(self, request, pk=None):
        service_item = self.get_object()
        logs = service_item.audit_logs.select_related('operator', 'undone_by').all()
        serializer = AuditLogSerializer(logs, many=True)
        return APIResponse(data=serializer.data)

    @action(detail=False, methods=['get'])
    def status_options(self, request):
        options = [{'value': s.value, 'label': s.label} for s in ServiceStatus]
        return APIResponse(data=options)

    @action(detail=False, methods=['get'])
    def operation_type_options(self, request):
        options = [{'value': o.value, 'label': o.label} for o in OperationType]
        return APIResponse(data=options)
