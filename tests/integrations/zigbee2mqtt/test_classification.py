"""Zigbee2MQTT's classification snapshot: which class each listed device gets, by the fields the rules read.

The integration maintainer's guard on the other families: a family owns its rules, and one family's rule can take
another's device (families/__init__.py, the rule order), so a change that moves a device listed here fails until this
file, outside every family, is edited. It lists every class and every trap the rule order names; a family's own
tests, under families/, cover the rest of its rules.
"""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.classes import device_class

TUYA = "_TZ3000_abcdefgh"  # a Tuya ZCL manufacturer string with no record
TUYA_MCU = "_TZE200_abcdefgh"
COUNTDOWN = frozenset({"state", "countdown"})  # the exposes of a TS011F on Tuya's countdown, converter A
NO_COUNTDOWN = frozenset({"state"})
LIDL = ("Lidl", "HG06337")  # a rebadged TS011F: neither registry field shows Tuya
GLEDOPTO_TUYA = ("Gledopto", "GL-SPI-206P")  # Gledopto's definition, Tuya datapoint firmware
PLUG = ("Tuya", "TS011F_plug_1")


def device(registry, zigbee=None, definition=None, exposes=None) -> tuple[SimpleNamespace, dict]:
    """The fields the rules read: the registry's manufacturer and model_id, and, once bridge/devices lists the device,
    its Zigbee manufacturer and model, its definition's model and its device-wide exposes."""
    bridge = dict(zip(("zigbee_manufacturer", "zigbee_model"), zigbee or (), strict=False))
    if definition is not None:
        bridge["definition_model"] = definition
    if exposes is not None:
        bridge["exposes"] = exposes
    return SimpleNamespace(manufacturer=registry[0], model=None, model_id=registry[1]), bridge


def countdown_plug(manufacturer: str, definition: str = PLUG[1], exposes=COUNTDOWN):
    return device(PLUG, (manufacturer, "TS011F"), definition, exposes)


DEVICES = {
    # Hue: Z2M's own vendor string, the whole of it, with or without the Zigbee strings.
    "hue": (device(("Philips", "9290018217")), "hue"),
    "hue_with_strings": (device(("Philips", "9290018217"), ("Signify Netherlands B.V.", "LWA012")), "hue"),
    "philips_prefix": (device(("Philips Lighting", None)), "other"),
    # The vendor classes, on the registry.
    "sengled": (device(("Sengled", "E11-G13")), "sengled"),
    "sengled_with_strings": (device(("Sengled", "E11-G13"), ("sengled", "E11-G13")), "sengled"),
    "gledopto": (device(("Gledopto", "GL-C-008")), "gledopto"),
    "gledopto_zigbee_case": (device(("GLEDOPTO", "GL-S-007ZS")), "gledopto"),
    "gledopto_prefix": (device(("Gledopto Lighting", "GL-C-009")), "other"),
    # A Tuya device under another vendor's definition: that vendor's class, or `other`, until its strings arrive, then
    # its Tuya class.
    "gledopto_badged_tuya_before": (device(GLEDOPTO_TUYA), "gledopto"),
    "gledopto_badged_tuya_after": (device(GLEDOPTO_TUYA, (TUYA_MCU, "TS0601")), "tuya_mcu"),
    "sengled_badged_tuya_after": (device(("Sengled", "E11-G13"), (TUYA, "TS0001")), "tuya_zcl"),
    "lidl_before": (device(LIDL), "other"),
    "lidl_after": (device(LIDL, (TUYA, "TS011F")), "tuya_ts011f"),
    "lidl_switch_after": (device(LIDL, (TUYA, "TS0001")), "tuya_zcl"),
    # Among Tuya's rules on the Zigbee strings, the models go first: a TS011F's `_TZ3000_` manufacturer matches the
    # ZCL manufacturer pattern, and a TS0601's model the ZCL model pattern.
    "ts011f_against_zcl_manufacturer": (device(PLUG, (TUYA, "TS011F"), PLUG[1], NO_COUNTDOWN), "tuya_ts011f"),
    "ts0601_against_zcl_model": (device(("Moes", "ZM-105"), ("Moes", "TS0601")), "tuya_mcu"),
    "datapoint_manufacturer": (device(("Moes", "ZM-105"), (TUYA_MCU, "ZM-105")), "tuya_mcu"),
    "zcl_manufacturer": (device(LIDL, ("_TYZB01_abcdefgh", "HG06337")), "tuya_zcl"),
    "ts_model_not_tuya_s": (device(LIDL, ("Lidl", "TSV-1")), "other"),
    # Tuya's countdown plugs: the string reported harmed, then each Verified string, then the rest on converter A.
    "countdown_harmed": (countdown_plug("_TZ3000_gjnozsaz"), "tuya_countdown_harmed"),
    "countdown_0zfrhq4i": (countdown_plug("_TZ3000_0zfrhq4i"), "tuya_countdown_tz3000_0zfrhq4i"),
    "countdown_typdpbpg": (countdown_plug("_TZ3000_typdpbpg"), "tuya_countdown_tz3000_typdpbpg"),
    "countdown_gznh2xla": (countdown_plug("_TZ3000_gznh2xla"), "tuya_countdown_tz3000_gznh2xla"),
    "countdown_okaz9tjs": (countdown_plug("_TZ3000_okaz9tjs"), "tuya_countdown_tz3000_okaz9tjs"),
    "countdown_unrecorded": (countdown_plug(TUYA), "tuya_countdown"),
    "countdown_verified_string_no_expose": (
        countdown_plug("_TZ3000_0zfrhq4i", exposes=frozenset({"state"})),
        "tuya_ts011f",
    ),
    "countdown_datapoint_zot60": (countdown_plug("_TZ3218_pfnjjx6a", definition="ZOT60"), "tuya_ts011f"),
    # The registry fallbacks, for a Tuya device bridge/devices doesn't show yet: the models before the vendor and the
    # catch-all.
    "registry_ts011f": (device(PLUG), "tuya_ts011f"),
    "registry_ts0601": (device(("Tuya", "TS0601_switch")), "tuya_mcu"),
    "registry_vendor": (device(("Tuya", "ZG-101Z")), "tuya_zcl"),
    "registry_ts_model": (device(("Moes", "TS0002")), "tuya_zcl"),
    # No rule: the default class.
    "ikea": (device(("IKEA of Sweden", "LED1836G9")), "other"),
    "ikea_with_strings": (device(("IKEA of Sweden", "LED1836G9"), ("IKEA of Sweden", "TRADFRI bulb")), "other"),
    "nothing_known": (device((None, None)), "other"),
}


@pytest.mark.parametrize("name", DEVICES)
def test_each_listed_device_keeps_its_class(name):
    (registry, bridge), expected = DEVICES[name]

    assert device_class(registry, bridge) == expected


def test_the_snapshot_lists_every_class():
    assert {expected for _, expected in DEVICES.values()} == INTEGRATION.classes
