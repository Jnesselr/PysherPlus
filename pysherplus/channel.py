from typing import Callable, Any, Dict, List

from pysherplus.connection import Connection

# func(event_name, data) -> None
EventCallback = Callable[[str, Any], None]


class ChannelEventRegistrar(object):
    def __init__(self,
                 event_name: str,
                 register: Callable[[str, EventCallback], None],
                 unregister: Callable[[str, EventCallback], None]
                 ):
        self._event_name = event_name
        self._register = register
        self._unregister = unregister

    def register(self, callback: EventCallback):
        self._register(self._event_name, callback)

    def unregister(self, callback: EventCallback):
        self._unregister(self._event_name, callback)


class Channel(object):
    def __init__(self,
                 channel_name: str,
                 connection: Connection):
        self._channel_name = channel_name
        self._connection = connection
        self._event_callbacks: Dict[str, List[EventCallback]] = {}
        self._subscribe_submitted: bool = False
        self._is_subscribed: bool = False

    @property
    def subscribed(self) -> bool:
        if not self._connection.connected:
            self._is_subscribed = False  # Can't be subscribed if you're not connected. Sorry we didn't know earlier.

        return self._is_subscribed

    def _register(self, event_name: str, callback: EventCallback):
        self._event_callbacks.setdefault(event_name, []).append(callback)

        if not self._is_subscribed:
            self._connection.subscribe(self._channel_name, self._handle_event)
            self._subscribe_submitted = True

    def _unregister(self, event_name: str, callback: EventCallback):
        self._event_callbacks.setdefault(event_name, []).remove(callback)

        if len(self._event_callbacks[event_name]) == 0:
            del self._event_callbacks[event_name]

        if len(self._event_callbacks) == 0:
            self._connection.unsubscribe(self._channel_name)
            self._subscribe_submitted = False
            self._is_subscribed = False

    def __getitem__(self, event_name: str):
        return ChannelEventRegistrar(event_name, self._register, self._unregister)

    def trigger(self, event_name, data):
        """Trigger an event on this channel.  Only available for private or
        presence channels

        :param event_name: The name of the event.  Must begin with 'client-''
        :type event_name: str

        :param data: The data to send with the event.
        """
        if self._connection:
            if event_name.startswith("client-"):
                if self._channel_name.startswith("private-") or self._channel_name.startswith("presence-"):
                    self._connection.send_event(event_name, data, channel_name=self._channel_name)

    def _handle_event(self, event_name: str, data: Any):
        if event_name.startswith('pusher_internal'):
            if event_name == 'pusher_internal:subscription_succeeded':
                self._is_subscribed = True

            return

        if event_name in self._event_callbacks.keys():
            callback: EventCallback
            for callback in self._event_callbacks[event_name]:
                callback(event_name, data)

        if '*' in self._event_callbacks.keys():
            callback: EventCallback
            for callback in self._event_callbacks['*']:
                callback(event_name, data)
