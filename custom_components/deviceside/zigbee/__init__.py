"""The Zigbee catalog: a device's own Zigbee strings and sourced firmware facts that two Zigbee stacks' families both
read, one module per vendor family (docs/design.md, Catalog). Patterns and facts only: no levels,
no calls and no Home Assistant imports, as each stack proves its own calls and classes (proof follows the call and the
class). A module exists only where two stacks read the same string."""
