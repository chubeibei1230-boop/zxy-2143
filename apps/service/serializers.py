from rest_framework import serializers
from .models import (
    ServiceType, ServiceSite, ServiceItem, ServiceStatus,
    AuditLog, OperationType, STATUS_TRANSITIONS, FINAL_STATUSES
)
from apps.core.serializers import UserSerializer


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = ['id', 'name', 'code', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ServiceSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceSite
        fields = ['id', 'name', 'code', 'address', 'contact', 'phone', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ServiceItemListSerializer(serializers.ModelSerializer):
    service_type = ServiceTypeSerializer(read_only=True)
    site = ServiceSiteSerializer(read_only=True)
    creator = UserSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)
    reviewer = UserSerializer(read_only=True)
    status_display = serializers.CharField(read_only=True)

    class Meta:
        model = ServiceItem
        fields = [
            'id', 'item_no', 'title', 'service_type', 'site',
            'applicant_name', 'applicant_phone',
            'status', 'status_display',
            'creator', 'assignee', 'reviewer',
            'appointment_time', 'created_at', 'updated_at', 'version',
        ]


class ServiceItemDetailSerializer(serializers.ModelSerializer):
    service_type = ServiceTypeSerializer(read_only=True)
    site = ServiceSiteSerializer(read_only=True)
    creator = UserSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)
    reviewer = UserSerializer(read_only=True)
    status_display = serializers.CharField(read_only=True)
    is_final = serializers.BooleanField(read_only=True)
    available_transitions = serializers.SerializerMethodField()

    class Meta:
        model = ServiceItem
        fields = [
            'id', 'item_no', 'title',
            'service_type', 'service_type_id',
            'site', 'site_id',
            'applicant_name', 'applicant_phone', 'applicant_id_card',
            'description',
            'status', 'status_display', 'is_final', 'available_transitions',
            'creator', 'assignee', 'reviewer',
            'handler_note', 'review_note',
            'appointment_time',
            'accept_time', 'process_start_time', 'review_time', 'close_time',
            'cancel_time', 'cancel_reason',
            'created_at', 'updated_at', 'version',
        ]
        read_only_fields = [
            'id', 'item_no', 'status', 'status_display', 'is_final',
            'available_transitions', 'creator', 'assignee', 'reviewer',
            'accept_time', 'process_start_time', 'review_time', 'close_time',
            'cancel_time', 'cancel_reason', 'created_at', 'updated_at', 'version',
        ]

    def get_available_transitions(self, obj):
        return [
            {'value': s, 'label': ServiceStatus(s).label}
            for s in obj.get_available_transitions()
        ]


class ServiceItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceItem
        fields = [
            'title', 'service_type_id', 'site_id',
            'applicant_name', 'applicant_phone', 'applicant_id_card',
            'description', 'appointment_time',
        ]

    def validate(self, attrs):
        if not attrs.get('service_type_id'):
            raise serializers.ValidationError({'service_type_id': '请选择服务类型'})
        if not attrs.get('site_id'):
            raise serializers.ValidationError({'site_id': '请选择服务站点'})
        return attrs


class StatusTransitionSerializer(serializers.Serializer):
    target_status = serializers.ChoiceField(choices=ServiceStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    assignee_id = serializers.IntegerField(required=False, allow_null=True)
    handler_note = serializers.CharField(required=False, allow_blank=True)
    review_note = serializers.CharField(required=False, allow_blank=True)
    cancel_reason = serializers.CharField(required=False, allow_blank=True)


class FieldUpdateSerializer(serializers.Serializer):
    assignee_id = serializers.IntegerField(required=False, allow_null=True)
    handler_note = serializers.CharField(required=False, allow_blank=True)
    appointment_time = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default='')


class UndoRedoSerializer(serializers.Serializer):
    audit_log_id = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True, default='')


class AuditLogSerializer(serializers.ModelSerializer):
    operator = UserSerializer(read_only=True)
    undone_by = UserSerializer(read_only=True)
    operation_type_display = serializers.CharField(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'operation_type', 'operation_type_display', 'operation_note',
            'operator', 'undone_by', 'is_undone', 'undone_at',
            'before_snapshot', 'after_snapshot',
            'created_at',
        ]
