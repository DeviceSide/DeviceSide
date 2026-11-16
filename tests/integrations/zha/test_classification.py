"""The class ZHA gives each listed device: the integration maintainer's guard on the families. A family owns its rules
(families/<family>/), so a change there that moves a listed device to another class fails here until this file, which
is the integration's, is edited too. It lists a device of every class and one for each trap the order between the
families' rule groups is there for (families/__init__.py)."""

import pytest

from custom_components.deviceside.integrations.zha import classes

ZIGPY = "zigpy.zcl"  # a standard On/Off cluster, as a quirk keeping the standard command leaves it
MCU = "zhaquirks.tuya.mcu"

DEVICES = [
    # (manufacturer, model, the module that defines the On/Off cluster's command; the class)
    # Every class.
    ("Signify Netherlands B.V.", "LTA009", ZIGPY, "hue"),
    ("_TZE200_abcdefgh", "TS0601", MCU, "tuya_mcu"),
    ("_TZ3000_gjnozsaz", "TS011F", ZIGPY, "tuya_countdown_harmed"),
    ("_TZ3000_typdpbpg", "TS011F", ZIGPY, "tuya_countdown"),
    ("_TZ3210_abcdefgh", "TS0505B", ZIGPY, "tuya_zcl"),
    ("sengled", "E11-G13", ZIGPY, "sengled"),
    ("SONOFF", "SWV", ZIGPY, "sonoff_swv"),
    ("IKEA of Sweden", "TRADFRI bulb E27 WS opal 980lm", ZIGPY, "other"),
    # Hue's two manufacturer strings, newer above and older.
    ("Philips", "LCT001", ZIGPY, "hue"),
    # Datapoint before ZCL: a TS0601's model matches the ZCL model pattern, with or without its quirk.
    ("_TZE200_abcdefgh", "TS0601", None, "tuya_mcu"),
    ("Lidl", "TS0601", ZIGPY, "tuya_mcu"),
    # A datapoint device by its quirk alone: a ZCL manufacturer string, or none of Tuya's, and a model of its own.
    ("_TZ3000_uim07oem", "TS0601", MCU, "tuya_mcu"),
    ("_TZ3210_0jxeoadc", "TS0049", MCU, "tuya_mcu"),
    ("Lidl", "HG06337", MCU, "tuya_mcu"),
    ("_TZ3000_typdpbpg", "TS011F", "zhaquirks.tuya", "tuya_mcu"),
    # The datapoint manufacturer string without the model or the quirk.
    ("_TZE204_abcdefgh", "Something", ZIGPY, "tuya_mcu"),
    # The harmed string before the countdown models, on its model only.
    ("_TZ3000_gjnozsaz", "TS0001", ZIGPY, "tuya_countdown"),
    # The countdown models before the rest of Tuya's ZCL strings, whatever the manufacturer.
    ("_TZ3000_abcdefgh", "TS0001", ZIGPY, "tuya_countdown"),
    ("Lidl", "TS0004", ZIGPY, "tuya_countdown"),
    ("_TZ3000_abcdefgh", "TS0121", ZIGPY, "tuya_zcl"),
    ("_TYZB01_abcdefgh", "Plug", ZIGPY, "tuya_zcl"),
    ("Lidl", "TS0505B", ZIGPY, "tuya_zcl"),
    # Every Tuya rule before Sengled's: a Tuya device sold under Sengled's name keeps its Tuya class.
    ("Sengled", "TS0601", ZIGPY, "tuya_mcu"),
    ("Sengled", "TS011F", ZIGPY, "tuya_countdown"),
    ("sengled", "TS0505B", ZIGPY, "tuya_zcl"),
    ("SENGLED", "E1F-N5E", ZIGPY, "sengled"),
    # Sonoff's other devices, and a Tuya-looking string no rule reads: the default class.
    ("SONOFF", "ZBMINIR2", ZIGPY, "other"),
    ("_TYST11_abcdefgh", "abcdefgh", ZIGPY, "other"),
    # A string the interview didn't read places nothing, whatever the other says.
    (None, "TS011F", ZIGPY, None),
    ("_TZ3000_gjnozsaz", None, ZIGPY, None),
    ("Signify Netherlands B.V.", "", ZIGPY, None),
    ("", "SWV", MCU, None),
]


@pytest.mark.parametrize(("manufacturer", "model", "quirk", "expected"), DEVICES)
def test_device_class(manufacturer, model, quirk, expected):
    assert classes.device_class(manufacturer, model, quirk) == expected


def test_every_class_is_listed():
    assert {expected for *_strings, expected in DEVICES if expected is not None} == classes.CLASSES
