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
    # Hidden 'root' super-user — not visible to regular admins in any listing.
    # Root has all privileges (implies is_superuser + is_staff), and can see
    # everything including other root accounts. Regular admins cannot see,
    # edit, or delete root accounts.
    is_root = models.BooleanField(
        default=False,
        help_text='Hidden root user — invisible to regular admins'
    )
    date_joined = models.DateTimeField(default=timezone.now)
    last_face_login = models.DateTimeField(null=True, blank=True)
    kiosk_pin = models.CharField(
        max_length=6, blank=True,
        help_text='4-6 digit PIN for kiosk queue login (set in Profile)'
    )
    # Role-based access for the Displays Hub and counter views.
    ROLE_CHOICES = [
        ('', 'Staff (ordering only)'),
        ('kitchen', 'Kitchen Counter'),
        ('cafe_bar', 'Cafe Bar Counter'),
        ('kitchen_admin', 'Kitchen Admin (menus + events)'),
        ('admin', 'Administrator'),
    ]
    role = models.CharField(
        max_length=16, choices=ROLE_CHOICES, blank=True,
        help_text='Workstation role — controls access to counter views'
    )
    # Cafeteria credit system
    monthly_credit = models.DecimalField(
        max_digits=8, decimal_places=2, default=50.00,
        help_text='Monthly cafeteria credit allowance'
    )
    credit_balance = models.DecimalField(
        max_digits=8, decimal_places=2, default=0.00,
        help_text='Current cafeteria credit balance'
    )

    # Employment type — temp staff and interns auto-deactivate after their last day.
    STAFF_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('temp', 'Temp Staff'),
        ('intern', 'Intern'),
    ]
    staff_type = models.CharField(
        max_length=10, choices=STAFF_TYPE_CHOICES, default='permanent',
        help_text='Temp and Intern accounts are auto-disabled after contract end date'
    )
    contract_end_date = models.DateField(
        null=True, blank=True,
        help_text='Last working day — account auto-disabled after this date'
    )

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

    @property
    def is_admin_role(self):
        """True if user has admin privileges (is_staff, is_superuser, or role=admin)."""
        return self.is_staff or self.is_superuser or self.role == 'admin'

    @property
    def is_kitchen_admin(self):
        """True if user is a Kitchen Admin (menu + event-menu management, counter access)."""
        return self.is_admin_role or self.role == 'kitchen_admin'

    @property
    def is_kitchen_user(self):
        """True if user can access kitchen counter views."""
        return self.is_admin_role or self.role in ('kitchen', 'kitchen_admin')

    @property
    def is_cafe_bar_user(self):
        """True if user can access cafe bar counter."""
        return self.is_admin_role or self.role == 'cafe_bar'


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


class QueueTicket(models.Model):
    """Queue ticket issued to a user."""
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('serving', 'Now Serving'),
        ('served', 'Served'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(
        StaffUser, on_delete=models.CASCADE, related_name='queue_tickets'
    )
    number = models.PositiveIntegerField(
        help_text='Queue number for the day (auto-incremented)'
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)
    served_at = models.DateTimeField(null=True, blank=True)
    date = models.DateField(default=timezone.now, help_text='Queue date (resets daily)')

    class Meta:
        ordering = ['date', 'number']
        unique_together = ['date', 'number']

    def __str__(self):
        return f"Q{self.number:03d} — {self.user.display_name} ({self.get_status_display()})"

    @classmethod
    def next_number(cls, date=None):
        """Get the next queue number for the given date."""
        if date is None:
            date = timezone.localdate()
        last = cls.objects.filter(date=date).order_by('-number').first()
        return (last.number + 1) if last else 1


# ════════════════════════════════════════════════════════════════════════════
#  CAFETERIA MEAL ORDERING SYSTEM
# ════════════════════════════════════════════════════════════════════════════

class MenuItem(models.Model):
    """Menu item for Kitchen (Local/International) or Cafe Bar."""
    MENU_CHOICES = [
        ('halal', 'Local'),
        ('non_halal', 'International'),
        ('cafe_bar', 'Cafe Bar'),
    ]
    menu_type = models.CharField(max_length=16, choices=MENU_CHOICES)
    category = models.CharField(max_length=50, blank=True, help_text='e.g. Rice Meals, Noodles, Hot Drinks')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    staff_price = models.DecimalField(max_digits=6, decimal_places=2)
    public_price = models.DecimalField(max_digits=6, decimal_places=2)
    daily_quantity = models.PositiveIntegerField(default=0, help_text='Total daily stock (set at start of day)')
    quantity_remaining = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=3)
    is_available = models.BooleanField(default=True, help_text='Admin on/off toggle — overrides stock')
    is_vegetarian = models.BooleanField(default=False, help_text='Mark this dish as vegetarian')
    photo = models.ImageField(upload_to='menu/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    # Cafe Bar customizations: JSON list of {name, choices: [...]}
    customizations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['menu_type', 'display_order', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_menu_type_display()})'

    @property
    def is_sold_out(self):
        return self.quantity_remaining <= 0

    @property
    def is_low_stock(self):
        return 0 < self.quantity_remaining <= self.low_stock_threshold


class OrderingHours(models.Model):
    """Service windows for each menu type. Multiple windows per menu_type allowed."""
    MENU_CHOICES = [
        ('kitchen', 'Kitchen (Local + International)'),
        ('cafe_bar', 'Cafe Bar'),
    ]
    menu_type = models.CharField(max_length=16, choices=MENU_CHOICES)
    label = models.CharField(max_length=40, blank=True, help_text='e.g. Lunch, Dinner, Morning')
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_active = models.BooleanField(default=True)
    # Per-day toggles (Python weekday: Mon=0 … Sun=6). Defaults to every day
    # so existing rows keep their previous always-on behaviour after migration.
    mon = models.BooleanField(default=True)
    tue = models.BooleanField(default=True)
    wed = models.BooleanField(default=True)
    thu = models.BooleanField(default=True)
    fri = models.BooleanField(default=True)
    sat = models.BooleanField(default=True)
    sun = models.BooleanField(default=True)

    class Meta:
        ordering = ['menu_type', 'opens_at']

    def __str__(self):
        return f'{self.get_menu_type_display()} {self.label}: {self.opens_at}-{self.closes_at}'

    def applies_to_weekday(self, weekday: int) -> bool:
        """weekday: Python Date.weekday() (Mon=0 … Sun=6)."""
        return [self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun][weekday]


class Holiday(models.Model):
    """
    Closed-day calendar. Admin adds public holidays / special closures here;
    _is_menu_open() treats any matching date as closed for the selected
    scope.
    """
    SCOPE_CHOICES = [
        ('all', 'Everything closed'),
        ('kitchen', 'Kitchen only'),
        ('cafe_bar', 'Cafe Bar only'),
    ]
    date = models.DateField(unique=True)
    label = models.CharField(max_length=100, help_text='e.g. Christmas Day, Stock-take')
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default='all')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date:%d %b %Y} — {self.label}'

    def closes(self, menu_type: str) -> bool:
        if self.scope == 'all':
            return True
        if self.scope == 'kitchen' and menu_type in ('kitchen', 'halal', 'non_halal'):
            return True
        if self.scope == 'cafe_bar' and menu_type == 'cafe_bar':
            return True
        return False


class Order(models.Model):
    """A customer order (staff or public walk-in)."""
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('confirmed', 'Confirmed'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Collection'),
        ('collected', 'Collected'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('no_show', 'No Show'),
    ]
    MENU_CHOICES = [
        ('halal', 'Local'),
        ('non_halal', 'International'),
        ('cafe_bar', 'Cafe Bar'),
        ('mixed', 'Mixed'),
    ]
    PAYMENT_CHOICES = [
        ('credits', 'Staff Credits'),
        ('stripe', 'Stripe Card'),
        ('paynow', 'PayNow QR'),
        ('cash', 'Cash'),
        ('terminal', 'Terminal at Counter'),
        ('mixed', 'Credits + Card/PayNow'),
    ]

    order_number = models.CharField(max_length=10, unique=True, help_text='e.g. H031, C019, N028, P042')
    customer = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders', help_text='Null for public walk-in'
    )
    is_public = models.BooleanField(default=False)
    public_name = models.CharField(max_length=60, blank=True, help_text='For walk-in customers')

    menu_type = models.CharField(max_length=16, choices=MENU_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')

    subtotal = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    credits_applied = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=12, choices=PAYMENT_CHOICES, blank=True)

    # HMAC-signed QR token
    qr_token = models.CharField(max_length=200, unique=True, blank=True)
    qr_used = models.BooleanField(default=False)
    qr_used_at = models.DateTimeField(null=True, blank=True)

    # Payment QR for public "pay at counter" flow.
    # Customer prints this at the kiosk, takes it to cafe bar, staff scans
    # to process cash/card payment on the terminal.
    payment_token = models.CharField(max_length=200, blank=True)
    payment_received_at = models.DateTimeField(null=True, blank=True)
    payment_received_by = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments_received'
    )

    # Mixed-menu orders (kitchen + cafe bar in one cart) get an 'M' prefix.
    is_mixed = models.BooleanField(default=False)

    # Collection time for Cafe Bar scheduling (Now / +10 / +20 minutes)
    collection_time_minutes = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        name = self.customer.display_name if self.customer else (self.public_name or 'Public')
        return f'{self.order_number} — {name}'

    @classmethod
    def next_number(cls, menu_type: str, is_public: bool = False, is_mixed: bool = False) -> str:
        """
        Generate next order number for today with correct prefix.
        Prefix rules:
          M — mixed (items from multiple menus)
          P — public walk-in (single menu)
          H — Local (Halal) Kitchen
          N — International (Non-Halal) Kitchen
          C — Cafe Bar
        """
        from django.utils import timezone as tz
        if is_mixed:
            prefix = 'M'
        elif is_public:
            prefix = 'P'
        elif menu_type == 'halal':
            prefix = 'H'
        elif menu_type == 'non_halal':
            prefix = 'N'
        elif menu_type == 'cafe_bar':
            prefix = 'C'
        else:
            prefix = 'O'

        today_start = tz.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        last = cls.objects.filter(
            order_number__startswith=prefix,
            created_at__gte=today_start,
        ).order_by('-created_at').first()

        if last:
            try:
                last_num = int(last.order_number[1:])
            except ValueError:
                last_num = 0
        else:
            last_num = 0
        return f'{prefix}{last_num + 1:03d}'


class OrderItem(models.Model):
    """Line item in an order."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    name_snapshot = models.CharField(max_length=120, help_text='Name at time of order')
    price_snapshot = models.DecimalField(max_digits=6, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    customizations = models.JSONField(default=dict, blank=True)
    subtotal = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # Snapshot of the menu type at order time — survives menu_item deletion.
    # Also drives per-counter collection: items with menu_type='halal' can
    # only be collected from the halal kitchen, etc.
    menu_type_snapshot = models.CharField(max_length=16, blank=True)
    # When this specific item was collected at its counter. Null = not collected.
    collected_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.quantity}× {self.name_snapshot}'


class CreditTransaction(models.Model):
    """Ledger entry for every credit balance change."""
    TYPE_CHOICES = [
        ('allowance', 'Monthly Allowance'),
        ('order', 'Order Debit'),
        ('refund', 'Refund Credit'),
        ('admin_adjust', 'Admin Adjustment'),
        ('vending', 'Vending Machine'),
    ]
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name='credit_transactions')
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=8, decimal_places=2, help_text='Positive=credit, negative=debit')
    balance_after = models.DecimalField(max_digits=8, decimal_places=2)
    related_order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='success')
    machine_id = models.CharField(max_length=50, blank=True, help_text='Vending machine identifier')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.staff_id} {self.type} {self.amount}'


class QRScanLog(models.Model):
    """Audit log for every QR code scan at kitchen/cafe bar counters."""
    RESULT_CHOICES = [
        ('valid', 'Valid'),
        ('wrong_counter', 'Wrong Counter'),
        ('duplicate', 'Duplicate (already used)'),
        ('invalid', 'Invalid (tampered or unknown)'),
        ('not_ready', 'Not Ready'),
    ]
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    scanner_device = models.CharField(max_length=50, blank=True, help_text='e.g. halal_kitchen, cafe_bar')
    scanned_by = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='qr_scans'
    )
    result = models.CharField(max_length=16, choices=RESULT_CHOICES)
    token_preview = models.CharField(max_length=40, blank=True, help_text='First 40 chars of scanned token')
    scanned_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f'{self.get_result_display()} — {self.order_id} @ {self.scanned_at}'


class KioskConfig(models.Model):
    """
    Singleton holding runtime-editable kiosk timeouts (admin/root can
    change them without a redeploy).

    Access via KioskConfig.get() — it will create a default row on first
    use. Values are in SECONDS.
    """
    # Idle countdown on the kiosk landing screen (no login yet).
    idle_landing_seconds = models.PositiveIntegerField(
        default=15, help_text='Idle screen countdown before kiosk resets.'
    )
    # Idle auto-logout once a staff user is signed in OR public walk-in
    # is picking items (staff-login page, menu-select, menu browsing,
    # public_order).
    idle_session_seconds = models.PositiveIntegerField(
        default=30, help_text='Auto-logout after this many seconds of inactivity on any post-login kiosk screen.'
    )
    # After printing the receipt, how long to wait before auto-returning
    # the kiosk to the idle screen.
    post_print_seconds = models.PositiveIntegerField(
        default=5, help_text='Auto-return to idle screen this many seconds after Print is clicked.'
    )
    # Working days per month for credit proration when adding new staff.
    credit_working_days = models.PositiveIntegerField(
        default=30, help_text='Working days per month (used for prorating new staff credit).'
    )
    # Auto-cancellation: daily cutoff times after which uncollected orders
    # are marked as no-show and credits refunded.
    kitchen_cutoff_time = models.TimeField(
        default='17:01',
        help_text='Kitchen (Local + International) daily cutoff — uncollected orders auto-cancel after this time'
    )
    cafe_bar_cutoff_time = models.TimeField(
        default='20:01',
        help_text='Cafe Bar daily cutoff — uncollected orders auto-cancel after this time'
    )
    # Orders not collected within this many minutes are shown in the No Show tab.
    no_show_minutes = models.PositiveIntegerField(
        default=20,
        help_text='Minutes after order is ready before it appears as No Show at the counter'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Kiosk Configuration'

    def __str__(self):
        return f'KioskConfig (idle={self.idle_session_seconds}s, post-print={self.post_print_seconds}s)'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ═══ Events / Catering ═══════════════════════════════════════════════════════

class EventMenu(models.Model):
    """
    A catering-style event menu 'package' that staff can pick for team
    bonding, meetings, discussions, VIP events, etc. Composed of multiple
    EventMenuItem components (mains + sides + drinks + desserts).

    Created/edited by Admin or Kitchen Admin; refreshed monthly like the
    regular menu.
    """
    name = models.CharField(max_length=120, help_text='e.g. Executive Lunch Package, Asian Buffet')
    description = models.TextField(blank=True)
    price_per_pax = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    min_pax = models.PositiveIntegerField(default=10)
    max_pax = models.PositiveIntegerField(default=200)
    photo = models.ImageField(upload_to='event_menus/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    is_vegetarian = models.BooleanField(default=False, help_text='Entire package is vegetarian')
    display_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_event_menus',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class EventMenuItem(models.Model):
    """
    A component of an EventMenu: main course, side, drink, dessert, etc.
    Each EventMenu can have many items across multiple categories.
    """
    CATEGORY_CHOICES = [
        ('appetizer', 'Appetizer'),
        ('main',      'Main Course'),
        ('side',      'Side Dish'),
        ('drink',     'Drink'),
        ('dessert',   'Dessert'),
        ('other',     'Other'),
    ]
    event_menu = models.ForeignKey(EventMenu, on_delete=models.CASCADE, related_name='components')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    is_vegetarian = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['event_menu', 'category', 'display_order']

    def __str__(self):
        return f'{self.event_menu.name} / {self.get_category_display()}: {self.name}'


class EventBooking(models.Model):
    """
    Staff-submitted event booking awaiting admin approval.

    Flow:
      Staff creates via PWA (date must be >= today + 14 days) → 'pending'
      Admin approves on /cafeteria/admin/events/ → 'approved'
      Kitchen / Cafe Bar staff see it on their events list so they know
      what to prepare. Kitchen Admin sees the booker's staff details ONLY
      after the booking is approved.
    """
    EVENT_TYPE_CHOICES = [
        ('team_bonding', 'Team Bonding'),
        ('meeting',      'Meeting'),
        ('discussion',   'Discussion'),
        ('vip',          'VIP Event'),
        ('other',        'Other'),
    ]
    STATUS_CHOICES = [
        ('pending',   'Pending Approval'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    # Who + what
    booked_by = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True,
        related_name='event_bookings',
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    event_menu = models.ForeignKey(
        EventMenu, on_delete=models.PROTECT, related_name='bookings',
    )
    pax = models.PositiveIntegerField()
    event_date = models.DateField()
    event_time = models.TimeField()
    venue = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    title = models.CharField(max_length=160, blank=True, help_text='Optional event title (e.g. Q3 Offsite)')

    # Approval workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        StaffUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_event_bookings',
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-event_date', '-event_time']

    def __str__(self):
        return f'{self.get_event_type_display()} · {self.event_date} · {self.pax} pax'

    @property
    def total_cost(self):
        return (self.event_menu.price_per_pax or 0) * self.pax

    @property
    def is_approved(self):
        return self.status == 'approved'

    @property
    def is_pending(self):
        return self.status == 'pending'
