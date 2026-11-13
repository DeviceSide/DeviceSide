# Logging

A user's debug log is often all a bug report holds, so log for the first report: what DeviceSide sent, what the
device answered, and which way DeviceSide went because of it ([evidence rules](evidence.md#tenets), tenet 4). Every
module uses `_LOGGER = logging.getLogger(__name__)`.

## Levels

- **DEBUG:** each call you send, and each branch you take on a device's reply (a retry, a fallback, a read-back that
  failed, a skipped step), with the values that decided it.
- **INFO:** a lasting change you make to another system's settings, such as a Zigbee2MQTT option.
- **WARNING:** the device didn't get the command, or HA may now show the wrong state. Name the action, integration and
  entity, and the cause (timeout or error). End with the consequence: "…, so HA may show the old values".
- **`_LOGGER.exception`:** only in a background callback that must survive its own error.

## Each call sent

The integration's transport helpers log one DEBUG line per call, so an adapter that sends through them gets it for
free: `"<entity_id>: sending <transport> <command> <params>"`. A transport setting that changes what the call does on
the device rides the line (Zigbee2MQTT: `with {'hue_native_control': …}`). An adapter that sends some other way logs
the same line itself.

## What a line may name

Users paste logs into public issues.

- **Name the entity** (`light.kitchen`): it's how a log reads against the report. Where you hold only a device
  address, look up its entity (Hue: `bridge.entity_name`; Zigbee2MQTT: `addressing.entity_name`).
- **Never device addressing or secrets:** IEEE or MAC addresses, MQTT device topics, Zigbee2MQTT friendly names, Hue
  resource IDs, Shelly component IDs, Matter node IDs, tokens.
- **Upstream errors go through `core.errors.describe`**, never `%r` or `%s` at the call site: a call site can't tell
  which errors carry a secret, so one function decides. Most give their repr, as their text is often the diagnosis and
  HA logs them the same way. An HTTP client error's repr holds the request's URL and headers (a Hue bridge's app key)
  and its text the URL or the address it couldn't reach, so `describe` gives only its type, status and reason, or its
  errno name, for it or an error wrapping it, and its traceback stays out. A new client library whose errors carry
  addresses or secrets is handled in `describe`. Your own format strings never add an address to them. An import
  error is ours, not upstream, and is logged as it is.
- **A message another system wrote is not an upstream error.** An upstream error is an exception a library raises.
  A line another system logs or sends, such as a Zigbee2MQTT `bridge/logging` line, names devices its own way, so log
  the cause it names, never the line (Zigbee2MQTT: `bridge_cache.cause` and `scrub`).
- **Tests check it:** the Hue, ZHA and Zigbee2MQTT tests run at DEBUG and fail on a line that names an address their
  fixtures use: a quoted Hue resource ID; a ZHA IEEE; an IEEE, a device topic, a Zigbee2MQTT failure line, or a
  friendly name quoted or ahead of an endpoint (their `conftest.py`).

## Cost

A line that needs a lookup to build (an entity, a group's name) runs it only under `_LOGGER.isEnabledFor(DEBUG)`.
Formatting a payload you already hold is fine.
