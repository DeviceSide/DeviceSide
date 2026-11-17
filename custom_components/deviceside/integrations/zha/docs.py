"""Where the bundles ZHA's code cites are published: the bases of its sources (a refusal entry's `source` is an https
URL, which scripts/gen_compat.py checks)."""

from ...const import DOCS_URL

_BUNDLES = DOCS_URL + "docs/integrations/"
INTERNALS = _BUNDLES + "zha/internals.md"
# The Zigbee2MQTT bundle's research folder: the timed-on research ran there and covers both Zigbee stacks, so ZHA's
# entries cite it. Built here, not imported: importing Zigbee2MQTT's package would tie ZHA to it loading.
RESEARCH = _BUNDLES + "zigbee2mqtt/research/"
