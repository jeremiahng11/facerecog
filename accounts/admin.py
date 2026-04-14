from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    StaffUser, FaceLoginLog, AdminActionLog, QueueTicket,
    MenuItem, Order, OrderItem, CreditTransaction, QRScanLog, OrderingHours,
)


@admin.register(StaffUser)
class StaffUserAdmin(UserAdmin):
    list_display = ['staff_id', 'full_name', 'email', 'department',
                    'face_registered', 'face_enabled', 'is_active', 'date_joined']
    list_filter = ['face_registered', 'face_enabled', 'is_staff', 'is_active']
    search_fields = ['staff_id', 'email', 'full_name']
    ordering = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('staff_id', 'password')}),
        ('Personal', {'fields': ('full_name', 'email', 'department', 'profile_picture')}),
        ('Face Recognition', {'fields': ('face_photo', 'face_encoding', 'face_registered', 'face_enabled', 'last_face_login')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('staff_id', 'email', 'full_name', 'password1', 'password2'),
        }),
    )
    readonly_fields = ['last_face_login', 'face_photo']


@admin.register(FaceLoginLog)
class FaceLoginLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'success', 'confidence', 'ip_address', 'device']
    list_filter = ['success', 'device']
    readonly_fields = ['user', 'timestamp', 'success', 'confidence', 'ip_address', 'device', 'notes']


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ['admin_user', 'action', 'target_staff_id', 'target_name', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['admin_user', 'action', 'target_staff_id', 'target_name', 'details', 'timestamp']


@admin.register(QueueTicket)
class QueueTicketAdmin(admin.ModelAdmin):
    list_display = ['number', 'user', 'status', 'date', 'created_at', 'served_at']
    list_filter = ['status', 'date']
    search_fields = ['user__staff_id', 'user__full_name']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'menu_type', 'category', 'staff_price', 'public_price', 'quantity_remaining', 'is_available']
    list_filter = ['menu_type', 'is_available']
    search_fields = ['name', 'category']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    readonly_fields = ['name_snapshot', 'price_snapshot', 'quantity', 'subtotal']
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer', 'menu_type', 'status', 'subtotal', 'created_at']
    list_filter = ['status', 'menu_type']
    search_fields = ['order_number', 'customer__staff_id']
    readonly_fields = ['qr_token', 'qr_used', 'qr_used_at', 'created_at']
    inlines = [OrderItemInline]


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'amount', 'balance_after', 'created_at']
    list_filter = ['type']
    search_fields = ['user__staff_id']
    readonly_fields = ['user', 'type', 'amount', 'balance_after', 'related_order', 'notes', 'created_at']


@admin.register(QRScanLog)
class QRScanLogAdmin(admin.ModelAdmin):
    list_display = ['order', 'scanner_device', 'scanned_by', 'result', 'scanned_at']
    list_filter = ['result', 'scanner_device']


@admin.register(OrderingHours)
class OrderingHoursAdmin(admin.ModelAdmin):
    list_display = ['menu_type', 'label', 'opens_at', 'closes_at', 'is_active']
    list_filter = ['menu_type', 'is_active']
