from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    # Serve uploaded media files (face photos, profile pictures) from the
    # Railway Volume mounted at MEDIA_ROOT. Django's built-in `static()`
    # helper is a no-op when DEBUG=False, so we register the serve view
    # explicitly here. Wrapped in login_required so only authenticated
    # staff can retrieve face photos by URL.
    re_path(
        r'^media/(?P<path>.*)$',
        login_required(serve),
        {'document_root': settings.MEDIA_ROOT},
    ),
]
