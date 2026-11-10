DOMAIN = "deviceside"
NAME = "DeviceSide"

# The light.turn_on fields a action may accept, under their light.turn_on names.
LIGHT_FIELDS = ("brightness", "color_temp_kelvin", "hs_color", "rgb_color", "xy_color", "transition")

# Ceiling for one adapter's execute(): a target its gather() hasn't finished by then is rejected with timeout, and
# those that finished keep their results.
ADAPTER_TIMEOUT_S = 30
# Past the ceiling, the backstop for an execute() still running (work outside gather): every target gets timeout.
ADAPTER_BACKSTOP_S = 5

# Hue fades: hide the bridge's end-value and late reports from HA and show DeviceSide's predictions instead.
CONF_PREDICTED_STATE = "predicted_state"
PREDICTED_STATE_DEFAULT = True

# Lets a call touching an Experimental scope item through, instead of refusing it. Read by the dispatcher only.
CONF_EXPERIMENTAL = "experimental_features"
EXPERIMENTAL_DEFAULT = False

# Zigbee2MQTT: announce full-color lights to HA with both color modes, so HA takes the bulb's state in either.
CONF_Z2M_COLOR_MODES = "z2m_color_modes"
Z2M_COLOR_MODES_DEFAULT = True
