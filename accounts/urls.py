from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import queue_views

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

    # Queue System
    path('queue/kiosk/', queue_views.queue_kiosk_view, name='queue_kiosk'),
    path('queue/kiosk/generate/', queue_views.queue_kiosk_generate_ajax, name='queue_kiosk_generate'),
    path('queue/', queue_views.queue_dashboard_view, name='queue_dashboard'),
    path('queue/my-ticket/', queue_views.queue_my_ticket_view, name='queue_my_ticket'),
    path('queue/print/<int:ticket_id>/', queue_views.queue_print_view, name='queue_print'),
    path('queue/display/', queue_views.queue_display_view, name='queue_display'),
    path('queue/manage/', queue_views.queue_manage_view, name='queue_manage'),
    path('queue/api/status/', queue_views.queue_status_ajax, name='queue_status'),
    path('queue/api/generate/', queue_views.queue_generate_ajax, name='queue_generate'),
    path('queue/api/update/', queue_views.queue_update_ajax, name='queue_update'),

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
]
