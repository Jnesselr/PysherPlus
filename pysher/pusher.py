from urllib.parse import urlparse

from pysher.channel import Channel
from pysher.connection import Connection
import hashlib
import hmac
import logging
import json

VERSION = '0.6.0'


class PusherHost(object):
    _protocol_version = 7

    def __init__(self, key: str):
        self._key = key
        self._secret = ""

        self._client_id = "Pysher"
        self._host = "ws.pusherapp.com"
        self._path_prefix = ""
        self._secure = True
        self._port = 443

    @staticmethod
    def from_url(url: str):
        parsed = urlparse(url)

        scheme = parsed.scheme
        if scheme.startswith('http'):
            scheme = scheme.replace('http', 'ws')  # http -> ws and https -> wss
        if scheme not in ['ws', 'wss']:
            raise ValueError(f"Unknown scheme for url: {scheme}")

        port = parsed.port
        if not port:
            port = 80 if scheme == 'ws' else 443  # Secure port by default

        url_path = parsed.path
        if '/app/' not in url_path:
            raise ValueError(f"Cannot parse URL path. Expected to find '/app/' in '{url_path}'")
        path_prefix, key = url_path.split('/app/')

        return PusherHost(key) \
            .host(parsed.hostname) \
            .port(port) \
            .path_prefix(path_prefix) \
            .secure(scheme == "wss")

    @property
    def key(self) -> str:
        return self._key

    @property
    def key_as_bytes(self):
        return self._key.encode('UTF-8')

    @property
    def secret_as_bytes(self):
        return self._secret.encode('UTF-8')

    @property
    def url(self):
        path = f"{self._path_prefix}/app/{self._key}" \
               f"?client={self._client_id}&version={VERSION}&protocol={self._protocol_version}"

        if path.startswith('/'):
            path = path[1:]

        scheme = "wss" if self._secure else "ws"

        return f"{scheme}://{self._host}:{self._port}/{path}"

    def cluster(self, name: str):
        # https://pusher.com/docs/clusters
        self._host = f"ws-{name}.pusher.com"
        return self

    def host(self, hostname: str):
        self._host = hostname
        return self

    def port(self, port: int):
        self._port = port
        return self

    def path_prefix(self, prefix: str):
        self._path_prefix = prefix
        return self

    def secure(self, is_secure: bool):
        self._secure = is_secure
        return self

    def secret(self, secret: str):
        self._secret = secret
        return self


class Pusher(object):
    client_id = "Pysher"
    protocol = 6

    def __init__(self, host: PusherHost, user_data=None, log_level=logging.INFO,
                 daemon=True, reconnect_interval=10, auto_sub=False):
        """Initialize the Pusher instance.


        :param Optional[Dict] user_data:
        :param str log_level:
        :param bool daemon:
        :param int or float reconnect_interval:
        :param bool auto_sub:
        """
        self.host: PusherHost = host
        self.url = host.url
        self.key = host.key

        self.user_data = user_data or {}

        self.channels = {}

        if auto_sub:
            reconnect_handler = self._reconnect_handler
        else:
            reconnect_handler = None

        self.connection = Connection(self._connection_handler, self.url,
                                     reconnect_handler=reconnect_handler,
                                     log_level=log_level,
                                     daemon=daemon,
                                     reconnect_interval=reconnect_interval,
                                     socket_kwargs=dict(ping_timeout=100))

    def connect(self):
        """Connect to Pusher"""
        self.connection.start()

    def disconnect(self, timeout=None):
        """Disconnect from Pusher"""
        self.connection.disconnect(timeout)
        self.channels = {}

    def subscribe(self, channel_name, auth=None):
        """Subscribe to a channel.

        :param str channel_name: The name of the channel to subscribe to.
        :param str auth: The token to use if authenticated externally.
        :rtype: pysher.Channel
        """
        data = {'channel': channel_name}
        if auth is None:
            if channel_name.startswith('presence-'):
                data['auth'] = self._generate_presence_token(channel_name)
                data['channel_data'] = json.dumps(self.user_data)
            elif channel_name.startswith('private-'):
                data['auth'] = self._generate_auth_token(channel_name)
        else:
            data['auth'] = auth

        self.connection.send_event('pusher:subscribe', data)

        self.channels[channel_name] = Channel(channel_name, self.connection)

        return self.channels[channel_name]

    def unsubscribe(self, channel_name):
        """Unsubscribe from a channel

        :param str channel_name: The name of the channel to unsubscribe from.
        """
        if channel_name in self.channels:
            self.connection.send_event(
                'pusher:unsubscribe', {
                    'channel': channel_name,
                }
            )
            del self.channels[channel_name]

    def channel(self, channel_name):
        """Get an existing channel object by name

        :param str channel_name: The name of the channel you want to retrieve
        :rtype: pysher.Channel or None
        """
        return self.channels.get(channel_name)

    def _connection_handler(self, event_name, data, channel_name):
        """Handle incoming data.

        :param str event_name: Name of the event.
        :param Any data: Data received.
        :param str channel_name: Name of the channel this event and data belongs to.
        """
        if channel_name in self.channels:
            self.channels[channel_name]._handle_event(event_name, data)

    def _reconnect_handler(self):
        """Handle a reconnect."""
        for channel_name, channel in self.channels.items():
            data = {'channel': channel_name}

            if channel.auth:
                data['auth'] = channel.auth

            self.connection.send_event('pusher:subscribe', data)

    def _generate_auth_token(self, channel_name):
        """Generate a token for authentication with the given channel.

        :param str channel_name: Name of the channel to generate a signature for.
        :rtype: str
        """
        subject = f"{self.connection.socket_id}:{channel_name}"
        h = hmac.new(self.host.secret_as_bytes, subject.encode('utf-8'), hashlib.sha256)
        auth_key = f"{self.key}:{h.hexdigest()}"

        return auth_key

    def _generate_presence_token(self, channel_name):
        """Generate a presence token.

        :param str channel_name: Name of the channel to generate a signature for.
        :rtype: str
        """
        subject = f"{self.connection.socket_id}:{channel_name}:{json.dumps(self.user_data)}"
        h = hmac.new(self.host.secret_as_bytes, subject.encode('utf-8'), hashlib.sha256)
        auth_key = f"{self.key}:{h.hexdigest()}"

        return auth_key
