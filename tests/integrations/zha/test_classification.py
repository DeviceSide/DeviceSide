"""The class ZHA gives each listed device: the integration maintainer's guard on the families. A family owns its rules
(families/<family>/), so a change there that moves a listed device to another class fails here until this file, which
is the integration's, is edited too. It guards the catalog as well (zigbee/tuya.py), which Zigbee2MQTT's Tuya family
shares: an edit made for the other stack that moves a device here fails here.

It lists a device of every class, one for each trap the order between the families' rule groups is there for
(families/__init__.py), and one for each catalog string that alone decides a class. A family's own tests, under
families/, cover the rest of its rules."""

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
    # Datapoint before ZCL: a TS0601's model matches the ZCL model pattern, and a datapoint device with a ZCL
    # manufacturer string and a model of its own shows only by its quirk.
    ("Lidl", "TS0601", ZIGPY, "tuya_mcu"),
    ("_TZ3210_0jxeoadc", "TS0049", MCU, "tuya_mcu"),
    # The quirk before every other rule: a countdown model under a datapoint quirk, and another vendor's.
    ("_TZ3000_typdpbpg", "TS011F", "zhaquirks.tuya", "tuya_mcu"),
    ("sengled", "E11-G13", MCU, "tuya_mcu"),
    # Every Tuya rule before Sengled's and Sonoff's: a Tuya device sold under another name keeps its Tuya class.
    ("Sengled", "TS0601", ZIGPY, "tuya_mcu"),
    ("Sengled", "TS011F", ZIGPY, "tuya_countdown"),
    ("sengled", "TS0505B", ZIGPY, "tuya_zcl"),
    ("_TZ3000_abcdefgh", "SWV", ZIGPY, "tuya_zcl"),
    # The catalog: each of Tuya's Zigbee strings where it alone decides the class, and its nearest strings that aren't
    # Tuya's.
    ("_TZ3000_abcdefgh", "Plug", ZIGPY, "tuya_zcl"),
    ("_TZ3210_abcdefgh", "Plug", ZIGPY, "tuya_zcl"),
    ("_TYZB01_abcdefgh", "Plug", ZIGPY, "tuya_zcl"),
    ("_TYST11_abcdefgh", "abcdefgh", ZIGPY, "other"),
    ("_TZE200_abcdefgh", "Something", ZIGPY, "tuya_mcu"),
    ("_TZE204_abcdefgh", "Something", ZIGPY, "tuya_mcu"),
    ("Lidl", "TS0505B", ZIGPY, "tuya_zcl"),
    ("Lidl", "TS0601x", ZIGPY, "tuya_zcl"),
    ("Lidl", "TS130F", ZIGPY, "other"),
    ("Lidl", "TS011", ZIGPY, "other"),
    ("Lidl", "TSV-1", ZIGPY, "other"),
    # The catalog's harmed string, on its model alone, and its model under any other string.
    ("_TZ3000_gjnozsaz", "TS0001", ZIGPY, "tuya_countdown"),
    ("Lidl", "TS011F", ZIGPY, "tuya_countdown"),
]


@pytest.mark.parametrize(("manufacturer", "model", "quirk", "expected"), DEVICES)
def test_device_class(manufacturer, model, quirk, expected):
    assert classes.device_class(manufacturer, model, quirk) == expected


def test_every_class_is_listed():
    assert {expected for *_strings, expected in DEVICES} == classes.CLASSES.keys()
