#!/usr/bin/env python

import sys

from pysher.pusher import Pusher
import time

# Add a logging handler so that we can see the raw communication data
import logging

root = logging.getLogger()
root.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
root.addHandler(ch)


def channel_callback(event, data):
    print(f"Channel Callback: ({event}) {data}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <app_key>")
        sys.exit(1)

    app_key = sys.argv[1]

    pusher = Pusher(app_key)
    pusher['test_channel']['my_event'].register(channel_callback)

    pusher.connect()

    while True:
        time.sleep(1)
