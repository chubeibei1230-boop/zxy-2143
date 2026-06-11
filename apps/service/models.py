from django.db import models
from django.conf import settings
import json


class ServiceStatus(models.TextChoices):
    PENDING_ACCEPT = 'PENDING_ACCEPT', '待受理'
    PROCESSING = 'PROCESSING', '处理中'
    PENDING_REVIEW = 'PENDING_REVIEW', '待复核'
    CLOSED = 'CLOSED', '已关闭'
    CANCELLED = 'CANCELLED', '已取消'


class OperationType(models.TextChoices):
    CREATE = 'CREATE', '创建事项'
    STATUS_CHANGE = 'STATUS_CHANGE', '状态变更'
    ASSIGNEE_CHANGE = 'ASSIGNEE_CHANGE', '负责人变更'
    HANDLER_NOTE_CHANGE = 'HANDLER_NOTE_CHANGE', '处理说明修改'
    APPOINTMENT_CHANGE = 'APPOINTMENT_CHANGE', '预约时间调整'
    CANCEL = 'CANCEL', '取消事项'
    UNDO = 'UNDO', '撤销操作'
    REDO = 'REDO', '重做操作'


STATUS_TRANSITIONS = {
    ServiceStatus.PENDING_ACCEPT: [ServiceStatus.PROCESSING, ServiceStatus.CANCELLED],
    ServiceStatus.PROCESSING: [ServiceStatus.PENDING_REVIEW, ServiceStatus.CANCELLED],
    ServiceStatus.PENDING_REVIEW: [ServiceStatus.CLOSED, ServiceStatus.CANCELLED],
    ServiceStatus.CLOSED: [],
    ServiceStatus.CANCELLED: [],
}

FINAL_STATUSES = [ServiceStatus.CLOSED, ServiceStatus.CANCELLED]


class ServiceType(models.Model):
    name = models.CharField(max_length=100, verbose_name='服务类型名称')
    code = models.CharField(max_length=50, unique=True, verbose_name='服务类型编码')
    description = models.TextField(blank=True, verbose_name='描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'service_type'
        verbose_name = '服务类型'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class ServiceSite(models.Model):
    name = models.CharField(max_length=100, verbose_name='站点名称')
    code = models.CharField(max_length=50, unique=True, verbose_name='站点编码')
    address = models.CharField(max_length=255, blank=True, verbose_name='地址')
    contact = models.CharField(max_length=50, blank=True, verbose_name='联系人')
    phone = models.CharField(max_length=20, blank=True, verbose_name='联系电话')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'service_site'
        verbose_name = '服务站点'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class ServiceItem(models.Model):
    item_no = models.CharField(max_length=50, unique=True, verbose_name='事项编号')
    title = models.CharField(max_length=200, verbose_name='事项标题')
    service_type = models.ForeignKey(ServiceType, on_delete=models.PROTECT, verbose_name='服务类型')
    site = models.ForeignKey(ServiceSite, on_delete=models.PROTECT, verbose_name='服务站点')
    applicant_name = models.CharField(max_length=100, verbose_name='申请人姓名')
    applicant_phone = models.CharField(max_length=20, verbose_name='申请人电话')
    applicant_id_card = models.CharField(max_length=18, blank=True, verbose_name='申请人身份证')
    description = models.TextField(verbose_name='事项描述')
    status = models.CharField(
        max_length=20,
        choices=ServiceStatus.choices,
        default=ServiceStatus.PENDING_ACCEPT,
        verbose_name='状态',
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_items',
        verbose_name='创建人',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='assigned_items',
        null=True,
        blank=True,
        verbose_name='当前负责人',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reviewed_items',
        null=True,
        blank=True,
        verbose_name='复核人',
    )
    handler_note = models.TextField(blank=True, verbose_name='处理说明')
    review_note = models.TextField(blank=True, verbose_name='复核说明')
    appointment_time = models.DateTimeField(null=True, blank=True, verbose_name='预约时间')
    accept_time = models.DateTimeField(null=True, blank=True, verbose_name='受理时间')
    process_start_time = models.DateTimeField(null=True, blank=True, verbose_name='处理开始时间')
    review_time = models.DateTimeField(null=True, blank=True, verbose_name='复核时间')
    close_time = models.DateTimeField(null=True, blank=True, verbose_name='关闭时间')
    cancel_time = models.DateTimeField(null=True, blank=True, verbose_name='取消时间')
    cancel_reason = models.TextField(blank=True, verbose_name='取消原因')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    version = models.IntegerField(default=1, verbose_name='版本号')

    class Meta:
        db_table = 'service_item'
        verbose_name = '服务事项'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.item_no} - {self.title}'

    @property
    def status_display(self):
        return self.get_status_display()

    @property
    def is_final(self):
        return self.status in FINAL_STATUSES

    def can_transition_to(self, target_status):
        if self.status in FINAL_STATUSES:
            return False
        return target_status in STATUS_TRANSITIONS.get(self.status, [])

    def get_available_transitions(self):
        if self.status in FINAL_STATUSES:
            return []
        return STATUS_TRANSITIONS.get(self.status, [])

    def snapshot(self):
        return {
            'title': self.title,
            'service_type_id': self.service_type_id,
            'site_id': self.site_id,
            'applicant_name': self.applicant_name,
            'applicant_phone': self.applicant_phone,
            'applicant_id_card': self.applicant_id_card,
            'description': self.description,
            'status': self.status,
            'assignee_id': self.assignee_id,
            'reviewer_id': self.reviewer_id,
            'handler_note': self.handler_note,
            'review_note': self.review_note,
            'appointment_time': self.appointment_time.isoformat() if self.appointment_time else None,
            'accept_time': self.accept_time.isoformat() if self.accept_time else None,
            'process_start_time': self.process_start_time.isoformat() if self.process_start_time else None,
            'review_time': self.review_time.isoformat() if self.review_time else None,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'cancel_time': self.cancel_time.isoformat() if self.cancel_time else None,
            'cancel_reason': self.cancel_reason,
            'version': self.version,
        }

    def restore_from_snapshot(self, snapshot):
        from django.utils import dateparse
        for field in ['title', 'applicant_name', 'applicant_phone', 'applicant_id_card',
                      'description', 'status', 'handler_note', 'review_note', 'cancel_reason']:
            if field in snapshot:
                setattr(self, field, snapshot[field])
        for fk_field in ['service_type_id', 'site_id', 'assignee_id', 'reviewer_id']:
            if fk_field in snapshot:
                setattr(self, fk_field, snapshot[fk_field])
        for dt_field in ['appointment_time', 'accept_time', 'process_start_time',
                         'review_time', 'close_time', 'cancel_time']:
            val = snapshot.get(dt_field)
            if val:
                setattr(self, dt_field, dateparse.parse_datetime(val))
            else:
                setattr(self, dt_field, None)
        if 'version' in snapshot:
            self.version = snapshot['version']


class AuditLog(models.Model):
    service_item = models.ForeignKey(
        ServiceItem,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        verbose_name='服务事项',
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name='操作人',
    )
    operation_type = models.CharField(
        max_length=30,
        choices=OperationType.choices,
        verbose_name='操作类型',
    )
    operation_note = models.TextField(blank=True, verbose_name='操作说明')
    before_snapshot = models.JSONField(default=dict, blank=True, verbose_name='变更前快照')
    after_snapshot = models.JSONField(default=dict, blank=True, verbose_name='变更后快照')
    is_undone = models.BooleanField(default=False, verbose_name='是否已撤销')
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='undone_logs',
        null=True,
        blank=True,
        verbose_name='撤销人',
    )
    undone_at = models.DateTimeField(null=True, blank=True, verbose_name='撤销时间')
    redo_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='redo_logs',
        verbose_name='重做对应的原操作',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作时间')

    class Meta:
        db_table = 'audit_log'
        verbose_name = '审计日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.service_item.item_no} - {self.get_operation_type_display()}'

    @property
    def operation_type_display(self):
        return self.get_operation_type_display()
