"""Control4's wire boundary for the call transcripts (tests/transcripts.py).

`director._call` is the one place a request reaches the Director: `read_variables` (a GET of an item's variables URI)
and `send` (a POST of a command and its params to the item's commands URI) both go through it. Its args are the wire
call: the request method (`send_get_request` or `send_post_request`), the URI and, for a command, its name and
params. Its reply is the Director's raw reply (or error). `hass` and `target` are dropped. It never calls itself,
and is only ever called directly."""

BOUNDARIES = [
    ("custom_components.deviceside.integrations.control4.director", "_call", 2),
]
