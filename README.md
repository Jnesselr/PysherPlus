[![PyPI version](https://badge.fury.io/py/PysherPlus.svg)](https://badge.fury.io/py/PysherPlus)

# Pysher

`pysherplus` is a python module for handling pusher websockets. It is based on @deepbrok's fork of  @ekulyk's `PythonPusherClient`. 
You can check out the deepbrook fork [here](https://github.com/deepbrook/Pysher). Deepbrook's code was in maintenance mode, and I wanted a more actively maintained project with a few bug fixes to use in a project.

## New features

- Subscription status of channels is automatically maintained and can be setup before connection.
- Authorization support for known secret, url based (such as Laravel), and even custom websocket authentication.
- Better support for custom URLs using the PusherHost class.

## Installation

Install via pip `pip install pysherplus`.

This module depends on websocket-client module available from: <http://github.com/websocket-client/websocket-client>

## Example

Example of using this pusher client to consume websockets:

```python
import sys
import time
from pysherplus.pusher import Pusher

# Add a logging handler so we can see the raw communication data
import logging

root = logging.getLogger()
root.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
root.addHandler(ch)

app_key = "my_pusher_app_key"
pusher = Pusher(app_key)


def my_func(event, data):
 print("processing Event:", event)
 print("processing Data:", data)


pusher["my_channel"]["my_event"].register(my_func)
pusher.connect()

while True:
 # Do other things in the meantime here...
 time.sleep(1)
```
    
## Performance
PysherPlus relies on websocket-client (websocket-client on pyPI, websocket import in code), which by default does utf8 validation in pure python. This is somewhat cpu hungry for lot's of messages (100's of KB/s or more). To optimize this validation consider installing the wsaccel module from pyPI to let websocket-client use C-compiled utf5 validation methods (websocket does this automatically once wsaccel is present and importable).

## Thanks
Huge thanks to @deepbrook for forking the original repo and by proxy, thank you to all of the people who [they thanked](https://github.com/deepbrook/Pysher#thanks). 

## Copyright

MTI License - See LICENSE for details.

# Changelog
## Version 2.0.0
Forked and refactored @deepbrook's code and republished under PysherPlus name.

For previous versions, see the original repo's [changelog](https://github.com/deepbrook/Pysher#changelog)