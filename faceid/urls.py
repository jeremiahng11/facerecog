from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.views.static import serve


def deny_face_photo(request, path):
    """
    Face photos are biometric data. They are deliberately NOT served over
    HTTP under any circumstances — not to the owner, not to admins, not
    to the server's own session. The file exists on the Railway Volume
    only so the server can re-extract the face encoding when asked to
    re-enrol a user; nothing in the UI needs to display the image itself.
    Any request to /media/face_photos/... returns 404.
    """
    raise Http404("Not available")


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),

    # Biometric lockdown: 404 every request for a face photo. This MUST
    # come before the generic /media/ route below so it takes precedence.
    re_path(r'^media/face_photos/', deny_face_photo),

    # Serve other uploaded media (profile pictures) from the Railway
    # Volume mounted at MEDIA_ROOT. Wrapped in login_required so
    # anonymous users cannot fetch profile pictures by URL either.
    re_path(
        r'^media/(?P<path>.*)$',
        login_required(serve),
        {'document_root': settings.MEDIA_ROOT},
    ),
]
