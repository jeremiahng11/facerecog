"""
WebSocket consumers for real-time updates.

Groups:
  tv-kitchen        — kitchen queue TV (H + N + P orders)
  tv-cafe-bar       — cafe bar TV (C orders)
  kitchen-<type>    — kitchen counter views (halal / non_halal / cafe_bar)
  admin-live        — admin dashboard live alerts (duplicate scans, locked IPs)
"""
import json
import logging

logger = logging.getLogger(__name__)

try:
    from channels.generic.websocket import AsyncWebsocketConsumer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False
    AsyncWebsocketConsumer = object


class OrderUpdatesConsumer(AsyncWebsocketConsumer):
    """
    A single consumer that subscribes to one or more groups based on
    the URL path parameter. The client opens:

      /ws/cafeteria/tv-kitchen/
      /ws/cafeteria/tv-cafe-bar/
      /ws/cafeteria/kitchen/halal/
      /ws/cafeteria/kitchen/non_halal/
      /ws/cafeteria/kitchen/cafe_bar/
      /ws/cafeteria/admin/
    """

    async def connect(self):
        self.group_name = self.scope['url_route']['kwargs'].get('group', 'tv-kitchen')
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Clients don't send anything — this is a server-push channel.
        pass

    async def order_event(self, event):
        """Forward a group message to the WebSocket client."""
        await self.send(text_data=json.dumps(event['payload']))


def push_order_event(group_name: str, event_type: str, data: dict):
    """
    Helper to push an event to a WebSocket group from synchronous code
    (e.g. views after an order status change).

    Usage:
        push_order_event('tv-kitchen', 'order_created', {'order_number': 'H001', ...})

    No-op if Channels is not installed or Redis is not configured.
    """
    if not CHANNELS_AVAILABLE:
        return
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(group_name, {
            'type': 'order.event',
            'payload': {'event': event_type, **data},
        })
    except Exception as e:
        logger.warning(f'push_order_event failed: {e}')
