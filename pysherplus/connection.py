import enum
import sched
from threading import Thread
from collections import defaultdict
from typing import Callable, Any, Dict, Optional

import websocket
import logging
import time
import json

from pysherplus.authentication import AuthResult, PysherAuthentication

ChannelCallback = Callable[[str, Any], None]


class ConnectionState(enum.Enum):
    INITIALIZED = enum.auto()
    FAILED = enum.auto()
    CONNECTING = enum.auto()
    CONNECTED = enum.auto()
    DISCONNECTED = enum.auto()


class Connection(object):
    def __init__(self,
                 url: str,
                 authenticator: Optional[PysherAuthentication] = None,
                 log_level=None,
                 reconnect_interval=10, socket_kwargs=None):
        self.url = url
        self._authenticator = authenticator

        self.socket = None
        self.socket_id: str = ""

        self.event_callbacks = defaultdict(list)

        self.disconnect_called = False
        self.needs_reconnect = False
        self.default_reconnect_interval = reconnect_interval
        self.reconnect_interval = reconnect_interval
        self.socket_kwargs = socket_kwargs or dict()

        self.pong_timer = None
        self.pong_received = False
        self.pong_timeout = 30

        self.bind("pusher:connection_established", self._connect_handler)
        self.bind("pusher:connection_failed", self._failed_handler)
        self.bind("pusher:pong", self._pong_handler)
        self.bind("pusher:ping", self._ping_handler)
        self.bind("pusher:error", self._pusher_error_handler)

        self.state: ConnectionState = ConnectionState.INITIALIZED

        self.logger = logging.getLogger(self.__module__)  # create a new logger

        if log_level:
            self.logger.setLevel(log_level)
            if log_level == logging.DEBUG:
                websocket.enableTrace(True)

        # From Martyn's comment at:
        # https://pusher.tenderapp.com/discussions/problems/36-no-messages-received-after-1-idle-minute-heartbeat
        #   "We send a ping every 5 minutes in an attempt to keep connections
        #   alive..."
        # This is why we set the connection timeout to 5 minutes, since we can
        # expect a pusher heartbeat message every 5 minutes.  Adding 5 sec to
        # account for small timing delays which may cause messages to not be
        # received in exact 5 minute intervals.

        self.connection_timeout = 35
        self.connection_timer = None

        self.ping_interval = 25
        self.ping_timer = None

        self.timeout_scheduler = sched.scheduler(
            time.time,
            sleep_max_n(min([self.pong_timeout, self.connection_timeout, self.ping_interval]))
        )
        self.timeout_scheduler_thread = None

        self._channels: Dict[str, ChannelCallback] = {}

        self._thread: Optional[Thread] = None

    @property
    def connected(self):
        return self.state == ConnectionState.CONNECTED

    def bind(self, event_name, callback, *args, **kwargs):
        """Bind an event to a callback

        :param event_name: The name of the event to bind to.
        :type event_name: str

        :param callback: The callback to notify of this event.
        """
        self.event_callbacks[event_name].append((callback, args, kwargs))

    def subscribe(self, channel_name: str, callback: ChannelCallback):
        if self.state == ConnectionState.CONNECTED:
            data = {'channel': channel_name}

            is_private = channel_name.startswith('private-')
            is_presence = channel_name.startswith('presence-')
            needs_auth = is_private or is_presence

            auth_result: Optional[AuthResult] = None
            if needs_auth:
                auth_result = self._authenticator.auth_token(self.socket_id, channel_name)

            if auth_result is not None:
                data['auth'] = auth_result.token

                if is_presence:
                    user_data = auth_result.user_data or {}

                    data['channel_data'] = json.dumps(user_data)

            self.send_event('pusher:subscribe', data)

        self._channels[channel_name] = callback

    def unsubscribe(self, channel_name: str):
        if channel_name in self._channels:
            if self.state == ConnectionState.CONNECTED:
                self.send_event(
                    'pusher:unsubscribe', {
                        'channel': channel_name,
                    }
                )
            del self._channels[channel_name]

    def disconnect(self, timeout=None):
        if self.state == ConnectionState.DISCONNECTED:
            return

        self.needs_reconnect = False
        self.disconnect_called = True
        if self.socket:
            self.socket.close()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def reconnect(self, reconnect_interval=None):
        if reconnect_interval is None:
            reconnect_interval = self.default_reconnect_interval

        self.logger.info("Connection: Reconnect in %s" % reconnect_interval)
        self.reconnect_interval = reconnect_interval

        self.needs_reconnect = True
        if self.socket:
            self.socket.close()

    def connect(self):
        if self.state == ConnectionState.CONNECTED:
            return

        if self._thread is None:
            self._thread = Thread(
                name="PysherEventLoop",
                target=self._run,
                daemon=True
            )
            self._thread.start()
        else:
            self.needs_reconnect = True

    def _run(self):
        self.state = ConnectionState.CONNECTING

        self.socket = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        self.socket.run_forever(**self.socket_kwargs)

        while self.needs_reconnect and not self.disconnect_called:
            self.logger.info("Attempting to connect again in %s seconds."
                             % self.reconnect_interval)
            self.state = ConnectionState.DISCONNECTED
            time.sleep(self.reconnect_interval)
            self.state = ConnectionState.CONNECTING

            # We need to set this flag since closing the socket will set it to
            # false
            self.socket.keep_running = True
            self.socket.run_forever(**self.socket_kwargs)

    def _on_open(self, *_):
        self.logger.info("Connection: Connection opened")

        # Send a ping right away to inform that the connection is alive. If you
        # don't do this, it takes the ping interval to subscribe to channel and
        # events
        self.send_ping()
        self._start_timers()

    def _on_error(self, *args):
        self.logger.info("Connection: Error - %s" % args[-1])
        self.state = ConnectionState.FAILED
        self.needs_reconnect = True

    def _on_message(self, *args):
        message = args[-1]
        self.logger.info("Connection: Message - %s" % message)

        # Stop our timeout timer, since we got some data
        self._stop_timers()

        params = self._parse(message)

        if 'event' in params.keys():
            event_name: str = params['event']
            if 'channel' not in params.keys():
                # We've got a connection event.  Let's handle it.
                if event_name in self.event_callbacks.keys():
                    for func, args, kwargs in self.event_callbacks[event_name]:
                        try:
                            func(params.get('data', None), *args, **kwargs)
                        except Exception:
                            self.logger.exception("Callback raised unhandled")
                else:
                    self.logger.info("Connection: Unhandled event")
            else:
                channel_name = params['channel']
                if channel_name in self._channels:
                    self._channels[channel_name](event_name, params.get('data'))

        # We've handled our data, so restart our connection timeout handler
        self._start_timers()

    def _on_close(self, *_):
        self.logger.info("Connection: Connection closed")
        self.state = ConnectionState.DISCONNECTED
        self._stop_timers()

    @staticmethod
    def _parse(message):
        return json.loads(message)

    def _stop_timers(self):
        for event in self.timeout_scheduler.queue:
            self._cancel_scheduler_event(event)

    def _start_timers(self):
        self._stop_timers()

        self.ping_timer = self.timeout_scheduler.enter(self.ping_interval, 1, self.send_ping)
        self.connection_timer = self.timeout_scheduler.enter(self.connection_timeout, 2, self._connection_timed_out)

        if not self.timeout_scheduler_thread:
            self.timeout_scheduler_thread = Thread(target=self.timeout_scheduler.run, daemon=True,
                                                   name="PysherScheduler")
            self.timeout_scheduler_thread.start()

        elif not self.timeout_scheduler_thread.is_alive():
            self.timeout_scheduler_thread = Thread(target=self.timeout_scheduler.run, daemon=True,
                                                   name="PysherScheduler")
            self.timeout_scheduler_thread.start()

    def _cancel_scheduler_event(self, event):
        try:
            self.timeout_scheduler.cancel(event)
        except ValueError:
            self.logger.info('Connection: Scheduling event already cancelled')

    def send_event(self, event_name, data, channel_name=None):
        """Send an event to the Pusher server.

        :param str event_name:
        :param Any data:
        :param str channel_name:
        """
        event = {'event': event_name, 'data': data}
        if channel_name:
            event['channel'] = channel_name

        self.logger.info("Connection: Sending event - %s" % event)
        try:
            self.socket.send(json.dumps(event))
        except Exception as e:
            self.logger.error("Failed send event: %s" % e)

    def send_ping(self):
        self.logger.info("Connection: ping to pusher")
        try:
            self.socket.send(json.dumps({'event': 'pusher:ping', 'data': ''}))
        except Exception as e:
            self.logger.error("Failed send ping: %s" % e)

        self.pong_timer = self.timeout_scheduler.enter(self.pong_timeout, 3, self._check_pong)

    def send_pong(self):
        self.logger.info("Connection: pong to pusher")
        try:
            self.socket.send(json.dumps({'event': 'pusher:pong', 'data': ''}))
        except Exception as e:
            self.logger.error("Failed send pong: %s" % e)

    def _check_pong(self):
        self._cancel_scheduler_event(self.pong_timer)

        if self.pong_received:
            self.pong_received = False
        else:
            self.logger.info("Did not receive pong in time.  Will attempt to reconnect.")
            self.state = ConnectionState.FAILED
            self.reconnect()

    def _connect_handler(self, data):
        parsed = json.loads(data)
        self.socket_id = parsed['socket_id']
        self.state = ConnectionState.CONNECTED

        # It's as if we've unsubscribed from all channels, so we clear our known channels and re-subscribe again
        current_channels: dict[str, ChannelCallback] = self._channels
        self._channels = {}
        for channel_name, callback in current_channels.items():
            self.subscribe(channel_name, callback)

    def _failed_handler(self, _):
        self.state = ConnectionState.FAILED

    def _ping_handler(self, _):
        self.send_pong()
        # Restart our timers since we received something on the connection
        self._start_timers()

    def _pong_handler(self, _):
        self.logger.info("Connection: pong from pusher")
        self.pong_received = True

    def _pusher_error_handler(self, data):
        if 'code' in data:

            try:
                error_code = int(data['code'])
            except BaseException:
                error_code = None

            if error_code is not None:
                self.logger.error("Connection: Received error %s" % error_code)

                if (error_code >= 4000) and (error_code <= 4099):
                    # The connection SHOULD NOT be re-established unchanged
                    self.logger.info("Connection: Error is unrecoverable.  Disconnecting")
                    self.disconnect()
                elif (error_code >= 4100) and (error_code <= 4199):
                    # The connection SHOULD be re-established after backing off
                    self.reconnect()
                elif (error_code >= 4200) and (error_code <= 4299):
                    # The connection SHOULD be re-established immediately
                    self.reconnect(0)
                else:
                    pass
            else:
                self.logger.error("Connection: Unknown error code")
        else:
            self.logger.error("Connection: No error code supplied")

    def _connection_timed_out(self):
        self.logger.info("Did not receive any data in time.  Reconnecting.")
        self.state = ConnectionState.FAILED
        self.reconnect()


def sleep_max_n(max_sleep_time):
    def sleep(time_to_sleep):
        time.sleep(min(max_sleep_time, time_to_sleep))

    return sleep
