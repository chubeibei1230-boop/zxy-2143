import uuid
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
            if self.operator.role not in [Role.OPERATOR_A, Role.OPERATOR_B, Role.ADMIN]:
                raise PermissionDeniedError('只有相关人员可以取消事项')
        return True

    def _check_operation_permission(self, operation_type, after_status=None):
        from apps.core.models import Role

        if self.operator.role == Role.ADMIN:
            return True

        if operation_type == OperationType.CREATE:
            raise PermissionDeniedError('只有管理员可以撤销创建操作')

        if operation_type == OperationType.STATUS_CHANGE and after_status:
            if after_status == ServiceStatus.PROCESSING:
                if self.operator.role not in [Role.OPERATOR_A, Role.ADMIN]:
                    raise PermissionDeniedError('只有录入员或管理员可以撤销受理操作')
            elif after_status == ServiceStatus.PENDING_REVIEW:
                if self.operator.role not in [Role.OPERATOR_A, Role.ADMIN]:
                    raise PermissionDeniedError('只有录入员或管理员可以撤销提交复核操作')
            elif after_status == ServiceStatus.CLOSED:
                if self.operator.role not in [Role.OPERATOR_B, Role.ADMIN]:
                    raise PermissionDeniedError('只有复核员或管理员可以撤销关闭操作')
            elif after_status == ServiceStatus.CANCELLED:
                raise PermissionDeniedError('已取消的操作不可撤销')

        if operation_type == OperationType.CANCEL:
            raise PermissionDeniedError('取消操作不可撤销')

        return True

    def _get_latest_undoable_log(self):
        return AuditLog.objects.filter(
            service_item=self.service_item,
            is_undone=False,
        ).exclude(
            operation_type__in=[OperationType.UNDO, OperationType.REDO]
        ).order_by('-created_at', '-id').first()

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
        latest_undoable = self._get_latest_undoable_log()
        if not latest_undoable:
            raise StateMachineError('没有可撤销的操作')

        if latest_undoable.id != audit_log_id:
            raise StateMachineError(
                f'只能撤销最近的一条操作（最近可撤销操作ID: {latest_undoable.id}）'
            )

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

        after_status = audit_log.after_snapshot.get('status')
        self._check_operation_permission(audit_log.operation_type, after_status)

        if audit_log.operation_type == OperationType.STATUS_CHANGE and after_status in FINAL_STATUSES:
            pass
        elif audit_log.operation_type == OperationType.STATUS_CHANGE:
            before_status = audit_log.before_snapshot.get('status')
            after_status_current = self.service_item.status
            if after_status != after_status_current:
                raise StateMachineError(
                    f'当前状态与操作后状态不一致，无法撤销。'
                    f'操作后状态应为 {ServiceStatus(after_status).label}，'
                    f'当前状态为 {ServiceStatus(after_status_current).label}'
                )
            if before_status and before_status not in STATUS_TRANSITIONS:
                if before_status not in FINAL_STATUSES:
                    raise StateMachineError(f'撤销后的目标状态 {ServiceStatus(before_status).label} 无效')

        before_snapshot_current = self.service_item.snapshot()

        self.service_item.restore_from_snapshot(audit_log.before_snapshot)
        self.service_item.version += 1
        self.service_item.save()

        after_snapshot_current = self.service_item.snapshot()

        audit_log.is_undone = True
        audit_log.undone_by = self.operator
        audit_log.undone_at = timezone.now()
        audit_log.save()

        AuditLog.objects.filter(
            service_item=self.service_item,
            redo_of=audit_log,
            is_undone=False
        ).update(
            is_undone=True,
            undone_by=self.operator,
            undone_at=timezone.now()
        )

        undo_note = f'撤销操作: {audit_log.get_operation_type_display()}'
        self._create_audit_log(
            OperationType.UNDO,
            before_snapshot_current,
            after_snapshot_current,
            undo_note,
        )

        return self.service_item

    def _get_latest_undone_log(self):
        return AuditLog.objects.filter(
            service_item=self.service_item,
            is_undone=True,
        ).exclude(
            operation_type__in=[OperationType.UNDO, OperationType.REDO]
        ).order_by('-created_at', '-id').first()

    @transaction.atomic
    def redo(self, audit_log_id):
        latest_undone = self._get_latest_undone_log()
        if not latest_undone:
            raise StateMachineError('没有可重做的操作')

        if latest_undone.id != audit_log_id:
            raise StateMachineError(
                f'只能重做最近被撤销的操作（最近可重做操作ID: {latest_undone.id}）'
            )

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

        target_status = original_log.after_snapshot.get('status')
        self._check_operation_permission(original_log.operation_type, target_status)

        current_status = self.service_item.status
        before_status_expected = original_log.before_snapshot.get('status')

        if original_log.operation_type == OperationType.STATUS_CHANGE:
            if before_status_expected and before_status_expected != current_status:
                raise StateMachineError(
                    f'当前状态与重做前预期状态不一致，无法重做。'
                    f'重做前状态应为 {ServiceStatus(before_status_expected).label}，'
                    f'当前状态为 {ServiceStatus(current_status).label}'
                )
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
    return f'SV{timezone.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:6].upper()}'
