"""WebSocket URL routing for Django Channels."""
from django.urls import re_path

try:
    from .consumers import OrderUpdatesConsumer
    websocket_urlpatterns = [
        re_path(r'^ws/cafeteria/(?P<group>[\w-]+(?:/[\w_]+)?)/$', OrderUpdatesConsumer.as_asgi()),
    ]
except ImportError:
    websocket_urlpatterns = []
