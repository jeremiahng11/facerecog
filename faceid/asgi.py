"""
ASGI application for the facerecog project.

Supports both HTTP (Django) and WebSocket (Channels) protocols.
Deploy with Daphne: daphne faceid.asgi:application
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faceid.settings')

# Initialize Django ASGI application early — this is needed before importing
# anything that depends on Django models.
django_asgi_app = get_asgi_application()

try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack

    from accounts.routing import websocket_urlpatterns

    application = ProtocolTypeRouter({
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    })
except ImportError:
    # Channels not installed yet — fall back to HTTP-only.
    application = django_asgi_app
