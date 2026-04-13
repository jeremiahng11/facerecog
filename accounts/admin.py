from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import StaffUser, FaceLoginLog


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
