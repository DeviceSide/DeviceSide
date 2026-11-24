"""ZCL facts shared by the ZHA, Zigbee2MQTT and Matter packages (Matter's OnOff cluster is ZCL's)."""

# A ZCL/Matter OnTime or TransitionTime is a uint16 in tenths of a second; 0xFFFF is reserved (OnTime) or the device's
# default (TransitionTime). It is specific to that encoding: a device counting in seconds keeps its own limit.
MAX_TENTHS_S = 0xFFFE / 10

ON_OFF_CLUSTER = 0x0006
ON_OFF = 0x0000
ON_TIME = 0x4001

# Level Control (0x0008) and Color Control (0x0300) clusters and the attributes Matter and ZHA both read, same IDs.
LEVEL_CLUSTER = 0x0008
CURRENT_LEVEL = 0x0000
ON_LEVEL = 0x0011
COLOR_CLUSTER = 0x0300
CURRENT_HUE = 0x0000
CURRENT_SATURATION = 0x0001
CURRENT_X = 0x0003
CURRENT_Y = 0x0004
COLOR_TEMPERATURE = 0x0007  # ColorTemperatureMireds

# Color Control's MoveMode (ZCL) and MoveModeEnum (Matter), one encoding: Up 1, Down 3 (0 is Stop, 2 reserved).
MOVE_UP = 0x01
MOVE_DOWN = 0x03

# Color capability bits, one layout in ZCL's ColorCapabilities (0x400A) and Matter's Color Control FeatureMap (0xFFFC).
HUE_SATURATION = 0x01
ENHANCED_HUE = 0x02
XY_COLOR = 0x08
TEMPERATURE_COLOR = 0x10

# A ZCL or Matter CurrentX and CurrentY (and ColorX/ColorY in MoveToColor) are the CIE coordinate in 1/65536 steps, 0 to
# 0xFEFF in use; a coordinate x in 0-1 is sent as round(x * XY_SCALE) and read as value / XY_SCALE.
XY_SCALE = 65535

# OnTime counts down live, so a read-back lands a little under the request: the slack the rig's ZHA timing allows, 3 s.
READBACK_SLACK_TENTHS = 30

# 0.4 s, the Hue bridge's default write fade, used for ExecuteIfOff writes so a call looks alike on every transport; a
# light that is off doesn't fade.
WRITE_FADE_TENTHS = 4
# That fade plus margin: a read sooner sees a mid-fade value.
WRITE_FADE_WAIT_S = 0.6
