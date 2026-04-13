from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import json


class StaffUserManager(BaseUserManager):
    def create_user(self, staff_id, email, password=None, **extra_fields):
        if not staff_id:
            raise ValueError('Staff ID is required')
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(staff_id=staff_id, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, staff_id, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('full_name', 'Administrator')
        return self.create_user(staff_id, email, password, **extra_fields)


class StaffUser(AbstractBaseUser, PermissionsMixin):
    staff_id = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    department = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(
        upload_to='profile_pics/', blank=True, null=True
    )
    # Face recognition data
    face_photo = models.ImageField(
        upload_to='face_photos/', blank=True, null=True,
        help_text='Primary face photo used for recognition'
    )
    face_encoding = models.TextField(
        blank=True, null=True,
        help_text='JSON-encoded face encoding vector'
    )
    face_registered = models.BooleanField(default=False)
    face_enabled = models.BooleanField(
        default=True,
        help_text='Allow this user to login via Face ID'
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_face_login = models.DateTimeField(null=True, blank=True)

    objects = StaffUserManager()

    USERNAME_FIELD = 'staff_id'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'Staff User'
        verbose_name_plural = 'Staff Users'

    def __str__(self):
        return f"{self.full_name} ({self.staff_id})"

    def get_face_encoding(self):
        """Deserialize face encoding from JSON"""
        if self.face_encoding:
            return json.loads(self.face_encoding)
        return None

    def set_face_encoding(self, encoding_list):
        """Serialize face encoding to JSON"""
        self.face_encoding = json.dumps(encoding_list)

    @property
    def display_name(self):
        return self.full_name or self.staff_id


class FaceLoginLog(models.Model):
    """Audit log for face recognition login attempts"""
    user = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='face_login_logs'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    confidence = models.FloatField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device = models.CharField(
        max_length=120, blank=True,
        help_text='Parsed device/browser info from User-Agent'
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.user} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class AdminActionLog(models.Model):
    """Audit trail for admin actions (user create/edit/delete)"""
    ACTION_CHOICES = [
        ('create', 'Created user'),
        ('edit', 'Edited user'),
        ('delete', 'Deleted user'),
        ('reencode', 'Re-encoded face'),
    ]
    admin_user = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True,
        related_name='admin_actions'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_staff_id = models.CharField(max_length=50)
    target_name = models.CharField(max_length=150, blank=True)
    details = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.admin_user} {self.action} {self.target_staff_id} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
