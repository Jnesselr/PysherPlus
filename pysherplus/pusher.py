import logging
from typing import Optional, Union
from urllib.parse import urlparse

from pysherplus.authentication import PysherAuthentication
from pysherplus.channel import Channel
from pysherplus.connection import Connection

VERSION = '2.0.1'  # TODO dedup this with the one in setup.py


class PusherHost(object):
    _protocol_version = 7

    def __init__(self, key: str):
        self._key = key

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


class Pusher(object):
    def __init__(self,
                 host: Union[str, PusherHost],
                 authenticator: Optional[PysherAuthentication] = None,
                 log_level=logging.INFO,
                 reconnect_interval=10):
        url = host  # Assume it's the host url
        if isinstance(host, str) and not host.startswith('ws'):
            # host is probably app key instead
            url = PusherHost(key=host).url
        elif isinstance(host, PusherHost):
            url = host.url

        self._channels = {}

        self._connection = Connection(url,
                                      authenticator,
                                      log_level=log_level,
                                      reconnect_interval=reconnect_interval,
                                      socket_kwargs=dict(ping_timeout=100))

    @property
    def connected(self):
        return self._connection.connected

    def connect(self):
        """Connect to Pusher"""
        self._connection.connect()

    def disconnect(self, timeout=None):
        """Disconnect from Pusher"""
        self._connection.disconnect(timeout)

    def __getitem__(self, channel_name: str) -> Channel:
        if channel_name not in self._channels:
            self._channels[channel_name] = Channel(channel_name, self._connection)

        return self._channels[channel_name]
