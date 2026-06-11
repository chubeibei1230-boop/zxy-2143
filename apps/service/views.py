from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import ServiceType, ServiceSite, ServiceItem, ServiceStatus, OperationType
from .serializers import (
    ServiceTypeSerializer, ServiceSiteSerializer,
    ServiceItemListSerializer, ServiceItemDetailSerializer, ServiceItemCreateSerializer,
    StatusTransitionSerializer, FieldUpdateSerializer, UndoRedoSerializer, AuditLogSerializer,
    TodoItemSerializer,
)
from .services import (
    ServiceItemStateMachine, create_service_item, generate_item_no,
    StateMachineError, PermissionDeniedError, InvalidTransitionError,
)
from apps.core.exceptions import APIResponse
from apps.core.permissions import IsAdmin, IsAdminOrOperatorA, IsAdminOrOperatorB
from apps.core.models import Role


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
        result_serializer = ServiceItemDetailSerializer(item, context={'request': request})
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

        result_serializer = ServiceItemDetailSerializer(item, context={'request': request})
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

        result_serializer = ServiceItemDetailSerializer(item, context={'request': request})
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

        result_serializer = ServiceItemDetailSerializer(item, context={'request': request})
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

        result_serializer = ServiceItemDetailSerializer(item, context={'request': request})
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


class WorkbenchViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ServiceItem.objects.select_related(
        'service_type', 'site', 'creator', 'assignee', 'reviewer'
    ).all()

    def _get_accessible_queryset(self, request):
        qs = self.get_queryset()
        user = request.user
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
        return qs

    def _get_todo_queryset(self, request):
        qs = self._get_accessible_queryset(request)
        user = request.user
        if user.is_admin:
            qs = qs.filter(~Q(status__in=[ServiceStatus.CLOSED, ServiceStatus.CANCELLED]))
        elif user.is_operator_a:
            qs = qs.filter(
                ~Q(status__in=[ServiceStatus.CLOSED, ServiceStatus.CANCELLED]),
                Q(creator=user) | Q(assignee=user)
            )
        elif user.is_operator_b:
            qs = qs.filter(
                Q(status=ServiceStatus.PENDING_REVIEW) |
                (Q(assignee=user) & ~Q(status__in=[ServiceStatus.CLOSED, ServiceStatus.CANCELLED])) |
                (Q(creator=user) & ~Q(status__in=[ServiceStatus.CLOSED, ServiceStatus.CANCELLED]))
            )
        return qs

    def _apply_filters(self, qs, request):
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        service_type_id = request.query_params.get('service_type_id')
        if service_type_id:
            qs = qs.filter(service_type_id=service_type_id)

        site_id = request.query_params.get('site_id')
        if site_id:
            qs = qs.filter(site_id=site_id)

        start_date = request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        keyword = request.query_params.get('keyword')
        if keyword:
            qs = qs.filter(
                Q(title__icontains=keyword) |
                Q(applicant_name__icontains=keyword) |
                Q(item_no__icontains=keyword)
            )

        return qs

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        user = request.user
        accessible_qs = self._get_accessible_queryset(request)
        todo_qs = self._get_todo_queryset(request)

        total_count = accessible_qs.count()
        pending_accept_count = accessible_qs.filter(status=ServiceStatus.PENDING_ACCEPT).count()
        processing_count = accessible_qs.filter(status=ServiceStatus.PROCESSING).count()
        pending_review_count = accessible_qs.filter(status=ServiceStatus.PENDING_REVIEW).count()
        closed_count = accessible_qs.filter(status=ServiceStatus.CLOSED).count()
        cancelled_count = accessible_qs.filter(status=ServiceStatus.CANCELLED).count()

        my_todo_count = todo_qs.count()
        my_created_count = accessible_qs.filter(creator=user).count()
        my_assigned_count = accessible_qs.filter(
            assignee=user,
        ).exclude(status__in=[ServiceStatus.CLOSED, ServiceStatus.CANCELLED]).count()
        my_review_count = accessible_qs.filter(
            status=ServiceStatus.PENDING_REVIEW
        ).count() if user.is_admin or user.is_operator_b else 0

        status_stats = [
            {'status': s.value, 'status_display': s.label,
             'count': accessible_qs.filter(status=s).count()}
            for s in ServiceStatus
        ]

        recent_todos = todo_qs.order_by('-updated_at')[:5]

        role_focus = self._get_role_focus(user)

        data = {
            'total_count': total_count,
            'pending_accept_count': pending_accept_count,
            'processing_count': processing_count,
            'pending_review_count': pending_review_count,
            'closed_count': closed_count,
            'cancelled_count': cancelled_count,
            'my_todo_count': my_todo_count,
            'my_created_count': my_created_count,
            'my_assigned_count': my_assigned_count,
            'my_review_count': my_review_count,
            'status_stats': status_stats,
            'recent_todos': TodoItemSerializer(recent_todos, many=True, context={'request': request}).data,
            'role_focus': role_focus,
        }

        return APIResponse(data=data)

    def _get_role_focus(self, user):
        if user.is_admin:
            return '全局概览：查看所有事项状态分布，监控整体进度'
        elif user.is_operator_a:
            return '重点关注：我创建的未完结事项、分配给我的待处理事项'
        elif user.is_operator_b:
            return '重点关注：待复核事项、分配给我的处理单'
        return ''

    @action(detail=False, methods=['get'], url_path='todos')
    def todos(self, request):
        qs = self._get_todo_queryset(request)
        qs = self._apply_filters(qs, request)
        qs = qs.order_by('-updated_at')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = TodoItemSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = TodoItemSerializer(qs, many=True, context={'request': request})
        return APIResponse(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='my-items')
    def my_items(self, request):
        qs = self._get_accessible_queryset(request)
        user = request.user

        item_type = request.query_params.get('type', 'all')
        if item_type == 'created':
            qs = qs.filter(creator=user)
        elif item_type == 'assigned':
            qs = qs.filter(assignee=user)
        elif item_type == 'review':
            if user.is_admin or user.is_operator_b:
                qs = qs.filter(status=ServiceStatus.PENDING_REVIEW)
            else:
                qs = qs.none()

        qs = self._apply_filters(qs, request)
        qs = qs.order_by('-created_at')

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = TodoItemSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = TodoItemSerializer(qs, many=True, context={'request': request})
        return APIResponse(data=serializer.data)
