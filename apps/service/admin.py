from django.contrib import admin
from .models import ServiceType, ServiceSite, ServiceItem, AuditLog


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(ServiceSite)
class ServiceSiteAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'contact', 'phone', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(ServiceItem)
class ServiceItemAdmin(admin.ModelAdmin):
    list_display = ['item_no', 'title', 'status', 'creator', 'assignee', 'created_at']
    list_filter = ['status', 'service_type', 'site']
    search_fields = ['item_no', 'title', 'applicant_name']
    readonly_fields = ['item_no', 'version']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['service_item', 'operation_type', 'operator', 'is_undone', 'created_at']
    list_filter = ['operation_type', 'is_undone']
    search_fields = ['service_item__item_no', 'operator__username']
    readonly_fields = [
        'service_item', 'operator', 'operation_type', 'operation_note',
        'before_snapshot', 'after_snapshot', 'is_undone', 'undone_by',
        'undone_at', 'redo_of', 'created_at',
    ]
