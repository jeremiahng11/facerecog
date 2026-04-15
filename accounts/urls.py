from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import cafeteria_views

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Password reset
    path('password-reset/', views.password_reset_view, name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url='/password-reset-complete/',
    ), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Face ID
    path('kiosk/', views.kiosk_view, name='kiosk'),
    path('face-login/', views.face_login_view, name='face_login'),
    path('api/face-verify/', views.face_verify_ajax, name='face_verify_ajax'),
    path('api/face-verify-fail/', views.face_verify_fail_ajax, name='face_verify_fail'),
    path('api/enroll-face/', views.enroll_face_ajax, name='enroll_face_ajax'),

    # Dashboard / Profile
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('api/my-face-photo/', views.my_face_photo_view, name='my_face_photo'),

    # (Queue system removed — cafeteria order flow replaces it)

    # Admin
    path('admin-panel/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-panel/users/', views.admin_users_view, name='admin_users'),
    path('admin-panel/users/add/', views.admin_add_user_view, name='admin_add_user'),
    path('admin-panel/users/<int:user_id>/edit/', views.admin_edit_user_view, name='admin_edit_user'),
    path('admin-panel/users/<int:user_id>/delete/', views.admin_delete_user_view, name='admin_delete_user'),
    path('admin-panel/users/<int:user_id>/reencode/', views.admin_reencode_user, name='admin_reencode_user'),
    path('admin-panel/face-logs/', views.admin_face_logs_view, name='admin_face_logs'),
    path('admin-panel/action-logs/', views.admin_action_logs_view, name='admin_action_logs'),
    path('admin-panel/bulk-import/', views.admin_bulk_import_view, name='admin_bulk_import'),

    # ═══ Cafeteria System ═══
    # Kiosk
    path('cafeteria/kiosk/', cafeteria_views.kiosk_idle_view, name='cafeteria_kiosk'),
    path('cafeteria/kiosk/staff-login/', cafeteria_views.kiosk_staff_login_view, name='cafeteria_staff_login'),
    path('cafeteria/kiosk/pin-login/', cafeteria_views.kiosk_pin_login_ajax, name='cafeteria_pin_login'),
    path('cafeteria/kiosk/menu-select/', cafeteria_views.kiosk_menu_select_view, name='cafeteria_menu_select'),
    path('cafeteria/kiosk/menu/<str:menu_type>/', cafeteria_views.kiosk_menu_view, name='cafeteria_menu'),
    path('cafeteria/kiosk/ticket/<int:order_id>/', cafeteria_views.kiosk_ticket_view, name='cafeteria_ticket'),
    path('cafeteria/kiosk/ticket/<int:order_id>/print/', cafeteria_views.kiosk_ticket_print_view, name='cafeteria_ticket_print'),

    # Ordering API
    path('cafeteria/api/place-order/', cafeteria_views.kiosk_place_order_ajax, name='cafeteria_place_order'),
    path('cafeteria/api/scan-qr/', cafeteria_views.kitchen_scan_qr_ajax, name='cafeteria_scan_qr'),

    # Kitchen / Cafe Bar counter views
    path('cafeteria/kitchen/<str:kitchen_type>/', cafeteria_views.kitchen_view, name='cafeteria_kitchen'),
    path('cafeteria/api/kitchen/mark-ready/<int:order_id>/', cafeteria_views.kitchen_mark_ready_ajax, name='cafeteria_mark_ready'),
    path('cafeteria/api/kitchen/mark-collected/<int:order_id>/', cafeteria_views.kitchen_mark_collected_ajax, name='cafeteria_mark_collected'),
    path('cafeteria/api/cafe-bar/complete-payment/<int:order_id>/', cafeteria_views.cafe_bar_complete_payment_ajax, name='cafeteria_complete_payment'),

    # Admin
    path('cafeteria/admin/menu/', cafeteria_views.admin_menu_list_view, name='cafeteria_admin_menu_list'),
    path('cafeteria/admin/menu/add/', cafeteria_views.admin_menu_add_view, name='cafeteria_admin_menu_add'),
    path('cafeteria/admin/menu/<int:item_id>/edit/', cafeteria_views.admin_menu_edit_view, name='cafeteria_admin_menu_edit'),
    path('cafeteria/admin/menu/<int:item_id>/toggle/', cafeteria_views.admin_menu_toggle_ajax, name='cafeteria_admin_menu_toggle'),
    path('cafeteria/admin/stock/', cafeteria_views.admin_stock_view, name='cafeteria_admin_stock'),
    path('cafeteria/admin/orders/', cafeteria_views.admin_orders_view, name='cafeteria_admin_orders'),
    path('cafeteria/admin/orders/<int:order_id>/cancel/', cafeteria_views.admin_cancel_order_ajax, name='cafeteria_admin_cancel_order'),
    path('cafeteria/admin/qr-logs/', cafeteria_views.admin_qr_logs_view, name='cafeteria_admin_qr_logs'),

    # ═══ Phase 2 additions ═══
    # TV Displays (no auth required)
    path('cafeteria/tv/kitchen/', cafeteria_views.tv_kitchen_queue_view, name='cafeteria_tv_kitchen'),
    path('cafeteria/tv/cafe-bar/', cafeteria_views.tv_cafe_bar_view, name='cafeteria_tv_cafe_bar'),
    path('cafeteria/api/tv-queue/', cafeteria_views.tv_queue_data_ajax, name='cafeteria_tv_queue_data'),

    # Cafe Bar counter
    path('cafeteria/cafe-bar/counter/', cafeteria_views.cafe_bar_counter_view, name='cafeteria_cafe_bar_counter'),

    # Public walk-in
    path('cafeteria/public/<str:menu_type>/', cafeteria_views.public_order_view, name='cafeteria_public'),
    path('cafeteria/public/ticket/<int:order_id>/', cafeteria_views.public_ticket_view, name='cafeteria_public_ticket'),
    path('cafeteria/public/ticket/<int:order_id>/print/', cafeteria_views.public_ticket_print_view, name='cafeteria_public_ticket_print'),
    path('cafeteria/api/public-place-order/', cafeteria_views.public_place_order_ajax, name='cafeteria_public_place_order'),

    # Staff Portal (mobile PWA)
    path('cafeteria/portal/', cafeteria_views.staff_portal_home_view, name='staff_portal_home'),
    path('cafeteria/portal/order/', cafeteria_views.staff_portal_order_view, name='staff_portal_order'),
    path('cafeteria/portal/qr/', cafeteria_views.staff_portal_qr_view, name='staff_portal_qr'),
    path('cafeteria/portal/history/', cafeteria_views.staff_portal_history_view, name='staff_portal_history'),
    path('cafeteria/portal/profile/', cafeteria_views.staff_portal_profile_view, name='staff_portal_profile'),

    # Admin dashboard/reports/staff/refunds
    path('cafeteria/admin/my-orders/', cafeteria_views.admin_my_orders_view, name='cafeteria_admin_my_orders'),
    path('cafeteria/admin/my-orders/new/', cafeteria_views.admin_new_order_view, name='cafeteria_admin_new_order'),
    path('cafeteria/admin/kiosk-config/', cafeteria_views.cafeteria_kiosk_config_view, name='cafeteria_kiosk_config'),
    path('cafeteria/admin/hours/', cafeteria_views.cafeteria_hours_view, name='cafeteria_admin_hours'),
    path('cafeteria/admin/dashboard/', cafeteria_views.cafeteria_dashboard_view, name='cafeteria_dashboard'),
    path('cafeteria/admin/reports/', cafeteria_views.cafeteria_reports_view, name='cafeteria_admin_reports'),
    path('cafeteria/admin/refunds/', cafeteria_views.cafeteria_refunds_view, name='cafeteria_admin_refunds'),
    path('cafeteria/admin/staff/', cafeteria_views.cafeteria_staff_view, name='cafeteria_admin_staff'),
    path('cafeteria/admin/staff/<int:user_id>/adjust/', cafeteria_views.cafeteria_staff_adjust_credit_ajax, name='cafeteria_staff_adjust'),
    path('cafeteria/admin/staff/<int:user_id>/role/', cafeteria_views.cafeteria_staff_role_ajax, name='cafeteria_staff_role'),
    path('cafeteria/admin/credits/', cafeteria_views.cafeteria_credits_bulk_view, name='cafeteria_credits_bulk'),
    path('cafeteria/admin/credit-history/', cafeteria_views.cafeteria_credit_history_view, name='cafeteria_credit_history'),
    path('cafeteria/admin/credit-history/<int:user_id>/', cafeteria_views.cafeteria_credit_history_view, name='cafeteria_credit_history_user'),
    path('cafeteria/displays/', cafeteria_views.cafeteria_displays_hub_view, name='cafeteria_displays_hub'),
    path('cafeteria/admin/displays/', cafeteria_views.cafeteria_displays_hub_view, name='cafeteria_displays_hub_admin'),

    # Stripe
    path('cafeteria/stripe/success/', cafeteria_views.stripe_success_view, name='cafeteria_stripe_success'),
    path('cafeteria/stripe/webhook/', cafeteria_views.stripe_webhook_view, name='cafeteria_stripe_webhook'),

    # Internal cron (GitHub Actions hits this; protected by CRON_SECRET)
    path('internal/reset-credits/', cafeteria_views.cron_reset_credits_view, name='cron_reset_credits'),
]
