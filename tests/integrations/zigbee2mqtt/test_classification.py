"""Zigbee2MQTT's classification snapshot: which class each listed device gets, by the fields the rules read.

The integration maintainer's guard on the other families: a family owns its rules, and one family's rule can take
another's device (families/__init__.py, the rule order), so a change that moves a device listed here fails until this
file, outside every family, is edited. It guards the catalog too (zigbee/tuya.py, zigbee/ikea.py), which ZHA's families
share: an edit made for the other stack that moves a device here fails here.

It lists a device of every class, with every field a rule could read where another family's rule could take it, one
for each trap the rule order names, and one for each catalog string that alone decides a class. A family's own tests,
under families/, cover the rest of its rules.
"""

from types import SimpleNamespace

import pytest

from custom_components.deviceside.integrations.zigbee2mqtt import INTEGRATION
from custom_components.deviceside.integrations.zigbee2mqtt.classes import device_class

TUYA = "_TZ3000_abcdefgh"  # a Tuya ZCL manufacturer string with no record
TUYA_MCU = "_TZE200_abcdefgh"
COUNTDOWN = frozenset({"state", "countdown"})  # the exposes of a TS011F on Tuya's countdown, converter A
NO_COUNTDOWN = frozenset({"state"})
# The exposes of another vendor's device that holds every property a Tuya rule reads, or could come to.
FULL = frozenset({"state", "brightness", "countdown"})
LIDL = ("Lidl", "HG06337")  # a rebadged TS011F: neither registry field shows Tuya
GLEDOPTO_TUYA = ("Gledopto", "GL-SPI-206P")  # Gledopto's definition, Tuya datapoint firmware
PLUG = ("Tuya", "TS011F_plug_1")
MOES = ("Moes", "ZM-105")  # a vendor and definition no registry rule reads


def device(registry, zigbee=None, definition=None, exposes=None) -> tuple[SimpleNamespace, dict]:
    """The fields the rules read: the registry's manufacturer and model_id, and, once bridge/devices lists the device,
    its Zigbee manufacturer and model, its definition's model and its device-wide exposes."""
    bridge = dict(zip(("zigbee_manufacturer", "zigbee_model"), zigbee or (), strict=False))
    if definition is not None:
        bridge["definition_model"] = definition
    if exposes is not None:
        bridge["exposes"] = exposes
    return SimpleNamespace(manufacturer=registry[0], model=None, model_id=registry[1]), bridge


def listed(registry, zigbee) -> tuple[SimpleNamespace, dict]:
    """Another vendor's device as bridge/devices lists it in full: its own Zigbee strings, its definition's model and
    FULL exposes, so a rule on any of them that isn't its family's has something to take."""
    return device(registry, zigbee, registry[1], FULL)


def countdown_plug(manufacturer: str):
    return device(PLUG, (manufacturer, "TS011F"), PLUG[1], COUNTDOWN)


def zigbee(manufacturer: str, model: str):
    """A device whose registry no rule reads, so its Zigbee strings alone decide."""
    return device(MOES, (manufacturer, model))


DEVICES = {
    # Every class but Tuya's: on the registry alone, and listed in full, where only its own family's rule may match.
    "hue": (device(("Philips", "9290018217")), "hue"),
    "hue_listed": (listed(("Philips", "9290018217"), ("Signify Netherlands B.V.", "LWA012")), "hue"),
    "sengled": (device(("Sengled", "E11-G13")), "sengled"),
    "sengled_listed": (listed(("Sengled", "E11-G13"), ("sengled", "E11-G13")), "sengled"),
    "gledopto": (device(("Gledopto", "GL-C-008")), "gledopto"),
    "gledopto_listed": (listed(("Gledopto", "GL-C-008"), ("GLEDOPTO", "GL-C-008")), "gledopto"),
    "other": (device(("Innr", "RB 285 C")), "other"),
    "other_listed": (listed(("Innr", "RB 285 C"), ("innr", "RB 285 C")), "other"),
    # IKEA's rules read its Zigbee strings alone: `other` until bridge/devices lists them.
    "ikea_before": (device(("IKEA", "LED1836G9")), "other"),
    "ikea_listed": (listed(("IKEA", "LED1836G9"), ("IKEA of Sweden", "TRADFRI bulb E27 WW 806lm")), "ikea"),
    "ikea_timer_harmed_listed": (
        listed(("IKEA", "LED2005R5/LED2106R3"), ("IKEA of Sweden", "TRADFRI bulb GU10 WS 345lm")),
        "ikea_timer_harmed",
    ),
    "nothing_known": (device((None, None)), "other"),
    # A Tuya device under another vendor's definition: that vendor's class, or `other`, until its strings arrive, then
    # its Tuya class.
    "gledopto_badged_tuya_before": (device(GLEDOPTO_TUYA), "gledopto"),
    "gledopto_badged_tuya_after": (device(GLEDOPTO_TUYA, (TUYA_MCU, "TS0601")), "tuya_mcu"),
    "sengled_badged_tuya_after": (device(("Sengled", "E11-G13"), (TUYA, "TS0001")), "tuya_zcl"),
    "lidl_before": (device(LIDL), "other"),
    "lidl_after": (device(LIDL, (TUYA, "TS011F")), "tuya_ts011f"),
    # Among Tuya's rules on the Zigbee strings, the models go first: a TS011F's `_TZ3000_` manufacturer matches the
    # ZCL manufacturer pattern, and a TS0601's model the ZCL model pattern.
    "ts011f_against_zcl_manufacturer": (device(PLUG, (TUYA, "TS011F"), PLUG[1], NO_COUNTDOWN), "tuya_ts011f"),
    "ts0601_against_zcl_model": (zigbee("Moes", "TS0601"), "tuya_mcu"),
    # The catalog: each of Tuya's Zigbee strings where it alone decides the class, and its nearest strings that aren't
    # Tuya's.
    "zcl_manufacturer_tz3000": (zigbee(TUYA, "ZM-105"), "tuya_zcl"),
    "zcl_manufacturer_tz3210": (zigbee("_TZ3210_abcdefgh", "ZM-105"), "tuya_zcl"),
    "zcl_manufacturer_tyzb01": (zigbee("_TYZB01_abcdefgh", "ZM-105"), "tuya_zcl"),
    "not_a_zcl_manufacturer_tyst11": (zigbee("_TYST11_abcdefgh", "abcdefgh"), "other"),
    "datapoint_manufacturer_tze200": (zigbee(TUYA_MCU, "ZM-105"), "tuya_mcu"),
    "datapoint_manufacturer_tze204": (zigbee("_TZE204_abcdefgh", "ZM-105"), "tuya_mcu"),
    "zcl_model_rebadged": (zigbee("Lidl", "TS0505B"), "tuya_zcl"),
    "zcl_model_longer_than_the_datapoint_one": (zigbee("Lidl", "TS0601x"), "tuya_zcl"),
    "not_a_zcl_model_three_digits": (zigbee("Lidl", "TS130F"), "other"),
    "not_a_zcl_model_ts011": (zigbee("Lidl", "TS011"), "other"),
    "not_a_zcl_model_ts_alone": (zigbee("Lidl", "TSV-1"), "other"),
    # Tuya's countdown plugs: the string reported harmed, each Verified string, and the rest on converter A.
    "countdown_harmed": (countdown_plug("_TZ3000_gjnozsaz"), "tuya_countdown_harmed"),
    "countdown_0zfrhq4i": (countdown_plug("_TZ3000_0zfrhq4i"), "tuya_countdown_tz3000_0zfrhq4i"),
    "countdown_typdpbpg": (countdown_plug("_TZ3000_typdpbpg"), "tuya_countdown_tz3000_typdpbpg"),
    "countdown_gznh2xla": (countdown_plug("_TZ3000_gznh2xla"), "tuya_countdown_tz3000_gznh2xla"),
    "countdown_okaz9tjs": (countdown_plug("_TZ3000_okaz9tjs"), "tuya_countdown_tz3000_okaz9tjs"),
    "countdown_unrecorded": (countdown_plug(TUYA), "tuya_countdown"),
    # The registry fallbacks, for a Tuya device bridge/devices doesn't show yet: the models before the vendor and the
    # catch-all.
    "registry_ts011f": (device(PLUG), "tuya_ts011f"),
    "registry_ts0601": (device(("Tuya", "TS0601_switch")), "tuya_mcu"),
    "registry_vendor": (device(("Tuya", "ZG-101Z")), "tuya_zcl"),
    "registry_ts_model": (device(("Moes", "TS0002")), "tuya_zcl"),
    # They run last, so they still place a device Z2M registers as Tuya's whose own Zigbee strings no rule reads.
    "registry_vendor_with_other_strings": (device(("Tuya", "ZG-101Z"), ("HOBEIAN", "ZG-101Z")), "tuya_zcl"),
    # And after the vendor rules: a device a vendor rule and a Tuya registry rule both match is the vendor's.
    "vendor_against_registry_ts_model": (device(("Sengled", "TS0505B")), "sengled"),
    "vendor_against_registry_ts_model_listed": (listed(("Gledopto", "TS0505B"), ("GLEDOPTO", "GL-C-008")), "gledopto"),
}


@pytest.mark.parametrize("name", DEVICES)
def test_each_listed_device_keeps_its_class(name):
    (registry, bridge), expected = DEVICES[name]

    assert device_class(registry, bridge) == expected


def test_the_snapshot_lists_every_class():
    assert {expected for _, expected in DEVICES.values()} == INTEGRATION.classes.keys()
