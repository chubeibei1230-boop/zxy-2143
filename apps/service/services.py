from django.utils import timezone
from django.db import transaction
from .models import (
    ServiceItem, ServiceStatus, OperationType, AuditLog,
    STATUS_TRANSITIONS, FINAL_STATUSES
)


class StateMachineError(Exception):
    pass


class PermissionDeniedError(StateMachineError):
    pass


class InvalidTransitionError(StateMachineError):
    pass


class ServiceItemStateMachine:
    def __init__(self, service_item: ServiceItem, operator):
        self.service_item = service_item
        self.operator = operator

    def _create_audit_log(self, operation_type, before_snapshot, after_snapshot, note='', redo_of=None):
        return AuditLog.objects.create(
            service_item=self.service_item,
            operator=self.operator,
            operation_type=operation_type,
            operation_note=note,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            redo_of=redo_of,
        )

    def _check_role_permission(self, target_status):
        from apps.core.models import Role

        if self.operator.role == Role.ADMIN:
            return True

        if target_status == ServiceStatus.PROCESSING:
            if self.operator.role not in [Role.OPERATOR_A, Role.ADMIN]:
                raise PermissionDeniedError('只有录入员或管理员可以受理事项')
        elif target_status == ServiceStatus.PENDING_REVIEW:
            if self.operator.role not in [Role.OPERATOR_A, Role.ADMIN]:
                raise PermissionDeniedError('只有录入员或管理员可以提交复核')
        elif target_status == ServiceStatus.CLOSED:
            if self.operator.role not in [Role.OPERATOR_B, Role.ADMIN]:
                raise PermissionDeniedError('只有复核员或管理员可以关闭事项')
        elif target_status == ServiceStatus.CANCELLED:
            pass
        return True

    @transaction.atomic
    def transition_to(self, target_status, note='', **kwargs):
        if self.service_item.status in FINAL_STATUSES:
            raise InvalidTransitionError('事项已处于终态，无法变更状态')

        if not self.service_item.can_transition_to(target_status):
            raise InvalidTransitionError(
                f'无法从 {self.service_item.get_status_display()} 转换到 {ServiceStatus(target_status).label}'
            )

        self._check_role_permission(target_status)

        before_snapshot = self.service_item.snapshot()

        self.service_item.status = target_status
        now = timezone.now()

        if target_status == ServiceStatus.PROCESSING:
            self.service_item.accept_time = now
            self.service_item.process_start_time = now
            if not self.service_item.assignee_id:
                self.service_item.assignee = self.operator
            if 'assignee_id' in kwargs and kwargs['assignee_id']:
                self.service_item.assignee_id = kwargs['assignee_id']
        elif target_status == ServiceStatus.PENDING_REVIEW:
            if 'handler_note' in kwargs:
                self.service_item.handler_note = kwargs['handler_note']
        elif target_status == ServiceStatus.CLOSED:
            self.service_item.review_time = now
            self.service_item.close_time = now
            self.service_item.reviewer = self.operator
            if 'review_note' in kwargs:
                self.service_item.review_note = kwargs['review_note']
        elif target_status == ServiceStatus.CANCELLED:
            self.service_item.cancel_time = now
            if 'cancel_reason' in kwargs:
                self.service_item.cancel_reason = kwargs['cancel_reason']

        self.service_item.version += 1
        self.service_item.save()

        after_snapshot = self.service_item.snapshot()

        operation_type = OperationType.CANCEL if target_status == ServiceStatus.CANCELLED else OperationType.STATUS_CHANGE
        self._create_audit_log(operation_type, before_snapshot, after_snapshot, note)

        return self.service_item

    @transaction.atomic
    def update_fields(self, operation_type, note='', **field_updates):
        if self.service_item.is_final and operation_type != OperationType.STATUS_CHANGE:
            pass

        before_snapshot = self.service_item.snapshot()
        changed = False

        for field, value in field_updates.items():
            if hasattr(self.service_item, field):
                setattr(self.service_item, field, value)
                changed = True

        if not changed:
            return self.service_item

        self.service_item.version += 1
        self.service_item.save()

        after_snapshot = self.service_item.snapshot()
        self._create_audit_log(operation_type, before_snapshot, after_snapshot, note)

        return self.service_item

    @transaction.atomic
    def undo(self, audit_log_id):
        try:
            audit_log = AuditLog.objects.select_for_update().get(
                id=audit_log_id,
                service_item=self.service_item,
            )
        except AuditLog.DoesNotExist:
            raise StateMachineError('审计记录不存在')

        if audit_log.is_undone:
            raise StateMachineError('该操作已被撤销，不可重复撤销')

        if audit_log.operation_type in [OperationType.UNDO, OperationType.REDO]:
            raise StateMachineError('不能撤销撤销/重做操作本身')

        from apps.core.models import Role
        if self.operator.role != Role.ADMIN:
            if audit_log.operation_type == OperationType.CREATE:
                raise PermissionDeniedError('只有管理员可以撤销创建操作')
            if audit_log.operation_type == OperationType.STATUS_CHANGE:
                before_status = audit_log.before_snapshot.get('status')
                after_status = audit_log.after_snapshot.get('status')
                if after_status == ServiceStatus.CLOSED and self.operator.role not in [Role.OPERATOR_B, Role.ADMIN]:
                    raise PermissionDeniedError('只有复核员或管理员可以撤销关闭操作')

        before_snapshot_current = self.service_item.snapshot()

        self.service_item.restore_from_snapshot(audit_log.before_snapshot)
        self.service_item.version += 1
        self.service_item.save()

        after_snapshot_current = self.service_item.snapshot()

        audit_log.is_undone = True
        audit_log.undone_by = self.operator
        audit_log.undone_at = timezone.now()
        audit_log.save()

        undo_note = f'撤销操作: {audit_log.get_operation_type_display()}'
        self._create_audit_log(
            OperationType.UNDO,
            before_snapshot_current,
            after_snapshot_current,
            undo_note,
        )

        return self.service_item

    @transaction.atomic
    def redo(self, audit_log_id):
        try:
            original_log = AuditLog.objects.select_for_update().get(
                id=audit_log_id,
                service_item=self.service_item,
            )
        except AuditLog.DoesNotExist:
            raise StateMachineError('审计记录不存在')

        if not original_log.is_undone:
            raise StateMachineError('该操作未被撤销，无法重做')

        if original_log.operation_type in [OperationType.UNDO, OperationType.REDO]:
            raise StateMachineError('不能重做撤销/重做操作本身')

        current_status = self.service_item.status
        target_status = original_log.after_snapshot.get('status')
        if target_status and target_status != current_status:
            if current_status not in FINAL_STATUSES and target_status not in STATUS_TRANSITIONS.get(current_status, []):
                raise InvalidTransitionError(
                    f'重做会导致非法状态转换: {ServiceStatus(current_status).label} -> {ServiceStatus(target_status).label}'
                )

        before_snapshot_current = self.service_item.snapshot()

        self.service_item.restore_from_snapshot(original_log.after_snapshot)
        self.service_item.version += 1
        self.service_item.save()

        after_snapshot_current = self.service_item.snapshot()

        original_log.is_undone = False
        original_log.undone_by = None
        original_log.undone_at = None
        original_log.save()

        redo_note = f'重做操作: {original_log.get_operation_type_display()}'
        self._create_audit_log(
            OperationType.REDO,
            before_snapshot_current,
            after_snapshot_current,
            redo_note,
            redo_of=original_log,
        )

        return self.service_item


def create_service_item(data, creator):
    from django.db import transaction

    with transaction.atomic():
        item = ServiceItem(
            item_no=data['item_no'],
            title=data['title'],
            service_type_id=data['service_type_id'],
            site_id=data['site_id'],
            applicant_name=data['applicant_name'],
            applicant_phone=data['applicant_phone'],
            applicant_id_card=data.get('applicant_id_card', ''),
            description=data['description'],
            status=ServiceStatus.PENDING_ACCEPT,
            creator=creator,
            appointment_time=data.get('appointment_time'),
        )
        item.save()

        before_snapshot = {}
        after_snapshot = item.snapshot()

        AuditLog.objects.create(
            service_item=item,
            operator=creator,
            operation_type=OperationType.CREATE,
            operation_note='创建事项',
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )

        return item


def generate_item_no():
    now = timezone.now()
    prefix = now.strftime('%Y%m%d%H%M%S')
    last = ServiceItem.objects.filter(item_no__startswith=prefix).order_by('-item_no').first()
    if last:
        try:
            seq = int(last.item_no[-4:]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:04d}'
