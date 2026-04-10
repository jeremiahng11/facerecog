from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Face ID
    path('face-login/', views.face_login_view, name='face_login'),
    path('api/face-verify/', views.face_verify_ajax, name='face_verify_ajax'),
    path('api/enroll-face/', views.enroll_face_ajax, name='enroll_face_ajax'),

    # Dashboard / Profile
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),

    # Admin user management
    path('admin-panel/users/', views.admin_users_view, name='admin_users'),
    path('admin-panel/users/add/', views.admin_add_user_view, name='admin_add_user'),
    path('admin-panel/users/<int:user_id>/edit/', views.admin_edit_user_view, name='admin_edit_user'),
    path('admin-panel/users/<int:user_id>/delete/', views.admin_delete_user_view, name='admin_delete_user'),
    path('admin-panel/users/<int:user_id>/reencode/', views.admin_reencode_user, name='admin_reencode_user'),
    path('admin-panel/face-logs/', views.admin_face_logs_view, name='admin_face_logs'),
]
