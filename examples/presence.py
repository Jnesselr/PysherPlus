#!/usr/bin/env python

import sys
import time

from pysherplus.authentication import KnownSecretAuthentication
from pysherplus.pusher import Pusher


def channel_callback(event, data):
    print(f"Channel Callback: ({event}) {data}")


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f"Usage: python {sys.argv[0]} <app_key> <secret> <user_id>")
        sys.exit(1)

    app_key = sys.argv[1]
    secret = sys.argv[2]
    user_id = sys.argv[3]

    auth = KnownSecretAuthentication(app_key, secret, user_data={'user_id': user_id})

    pusher = Pusher(app_key, auth)
    pusher['presence-channel']['my_event'].register(channel_callback)
    pusher.connect()

    while True:
        time.sleep(1)
