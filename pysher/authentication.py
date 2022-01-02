import abc
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Optional, Any, Union

import requests


@dataclass(frozen=True)
class AuthResult(object):
    token: str
    user_data: Optional[Any] = field(default=None)


class PysherAuthentication(abc.ABC):
    @abc.abstractmethod
    def auth_token(self, socket_id: str, channel_name: str) -> Optional[AuthResult]:
        pass


class KnownSecretAuthentication(PysherAuthentication):
    def __init__(self,
                 key: str,
                 secret: Union[str, bytes],
                 user_data: Optional[Any] = None):
        if isinstance(secret, str):
            secret = secret.encode('utf-8')

        self._key = key
        self._secret = secret
        self._user_data = user_data

    def auth_token(self, socket_id: str, channel_name: str) -> Optional[AuthResult]:
        is_presence_channel = channel_name.startswith('presence-')
        if is_presence_channel:
            subject = f"{socket_id}:{channel_name}"
        else:
            subject = f"{socket_id}:{channel_name}:{json.dumps(self._user_data)}"

        h = hmac.new(self._secret, subject.encode('utf-8'), hashlib.sha256)
        token = f"{self._key}:{h.hexdigest()}"

        return AuthResult(
            token=token,
            user_data=self._user_data if is_presence_channel else None
        )


class URLAuthentication(PysherAuthentication):
    def __init__(self,
                 url: str,
                 session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._url = url

    def auth_token(self, socket_id: str, channel_name: str) -> Optional[AuthResult]:
        response = self._session.post(
            self._url,
            json={
                'socket_id': socket_id,
                'channel_name': channel_name
            }
        )

        if not response.ok:
            return None

        response_json = response.json()

        return AuthResult(
            token=response_json['auth'],
            user_data=response_json['channel_data'] if 'channel_data' in response_json else None
        )
