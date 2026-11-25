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
# The exposes of a single-endpoint Tuya datapoint dimmer on Tuya's datapoint countdown.
DATAPOINT = frozenset({"state", "brightness", "countdown"})
PLUG = ("Tuya", "TS011F_plug_1")
SONOFF_ZBMINIR2 = ("SONOFF", "ZBMINIR2")
SONOFF_STRINGS = ("SONOFF", "ZBMINIR2")
INCHING = frozenset({"state", "inching_control_set"})
TUYA_WHD02 = ("_TZ3000_skueekg3", "TS0001")  # the WHD02, whose inching is measured
TUYA_MW781Z = ("_TZ300A_rncj86af", "TS0726")  # the Mowe MW781Z, whose inching is measured
TUYA_NO_EFFECT = ("_TZ3000_mzcp0of6", "TS0003")  # inching enabled in ZHC, reported having no effect
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
    # Aqara's rule reads the Zigbee string alone, so a registry-only device waits in `other`, and a bulb of Z2M's vendor
    # `Aqara` whose string is `LUMI` stays there.
    "aqara_before": (device(("Aqara", "T2_E27")), "other"),
    "aqara_listed": (listed(("Aqara", "T2_E27"), ("Aqara", "lumi.light.agl003")), "aqara"),
    "aqara_lumi_listed": (listed(("Aqara", "T1"), ("LUMI", "lumi.light.acn014")), "other"),
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
    # Sonoff's inching: by the definition's model and its device-wide composite, in bridge/devices alone.
    "sonoff_inching_before": (device(SONOFF_ZBMINIR2), "other"),
    "sonoff_inching": (device(SONOFF_ZBMINIR2, SONOFF_STRINGS, "ZBMINIR2", INCHING), "sonoff_inching"),
    "sonoff_inching_dimmer": (
        device(("SONOFF", "MINI-ZBDIM"), SONOFF_STRINGS, "MINI-ZBDIM", INCHING),
        "sonoff_inching",
    ),
    "sonoff_s60": (device(("SONOFF", "S60ZBTPF"), ("SONOFF", "S60ZBTPF"), "S60ZBTPF", INCHING), "sonoff_s60"),
    # The 2-gang's composite is per endpoint, so the device has none; and a model off the list, whatever it exposes.
    "sonoff_two_gang": (device(("SONOFF", "MINI-ZB2GS"), SONOFF_STRINGS, "MINI-ZB2GS", NO_COUNTDOWN), "other"),
    "sonoff_unlisted_model": (device(("SONOFF", "NEW-MODEL"), SONOFF_STRINGS, "NEW-MODEL", INCHING), "other"),
    # Tuya's inching: the two measured strings that expose the composite, ahead of the `tuya_zcl` rules that class them
    # otherwise (the WHD02's `_TZ3000_` string by manufacturer, the MW781Z's `TS0726` by model). Its TS000F variant (no
    # composite) and the string reported having no effect (composite exposed) stay `tuya_zcl`.
    "tuya_inching_whd02": (device(MOES, TUYA_WHD02, "WHD02", INCHING), "tuya_inching"),
    "tuya_inching_mw781z": (device(MOES, TUYA_MW781Z, "TS0726_1_gang_scene_switch", INCHING), "tuya_inching"),
    "tuya_inching_whd02_without_the_composite": (device(MOES, TUYA_WHD02, "WHD02", NO_COUNTDOWN), "tuya_zcl"),
    "tuya_inching_whd02_ts000f": (
        device(MOES, ("_TZ3000_skueekg3", "TS000F"), "TS000F_switch_module_1", NO_COUNTDOWN),
        "tuya_zcl",
    ),
    "tuya_inching_reported_no_effect": (
        device(MOES, TUYA_NO_EFFECT, "TS0003_switch_module_2", INCHING),
        "tuya_zcl",
    ),
    "tuya_inching_before": (device(("Tuya", "WHD02")), "tuya_zcl"),
    "nothing_known": (device((None, None)), "other"),
    # A Tuya device under another vendor's definition: that vendor's class, or `other`, until its strings arrive, then
    # its Tuya class.
    "gledopto_badged_tuya_before": (device(GLEDOPTO_TUYA), "gledopto"),
    "gledopto_badged_tuya_after": (device(GLEDOPTO_TUYA, (TUYA_MCU, "TS0601")), "tuya_mcu"),
    # And with its definition's countdown, Tuya's datapoint one, not Gledopto's class.
    "gledopto_badged_tuya_datapoint": (
        device(GLEDOPTO_TUYA, (TUYA_MCU, "TS0601"), GLEDOPTO_TUYA[1], DATAPOINT),
        "tuya_datapoint",
    ),
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
    # Tuya's datapoint countdown, a class per limit, on the definitions research names (families/tuya/datapoint.py).
    "datapoint": (
        device(("Tuya", "TS0601_dimmer_1_gang_1"), (TUYA_MCU, "TS0601"), "TS0601_dimmer_1_gang_1", DATAPOINT),
        "tuya_datapoint",
    ),
    "datapoint_24h": (
        device(("Tuya", "TS0601_multifunction_switch"), (TUYA_MCU, "TS0601"), "TS0601_multifunction_switch", COUNTDOWN),
        "tuya_datapoint_24h",
    ),
    "datapoint_2h": (device(("AVATTO", "ZBS16"), (TUYA_MCU, "TS0601"), "ZBS16", COUNTDOWN), "tuya_datapoint_2h"),
    # A TS011F with converter A's expose, yet a datapoint countdown: before the TS011F rules.
    "datapoint_zot60": (
        device(("AVATTO", "ZOT60"), ("_TZ3218_pfnjjx6a", "TS011F"), "ZOT60", COUNTDOWN),
        "tuya_datapoint",
    ),
    # Left out of the datapoint countdown, with a device-wide one: they keep their class. LYAI-14 reports a ZCL
    # manufacturer string, and switches by ZCL.
    "datapoint_left_out_lyai_14": (
        device(("Tuya", "LYAI-14"), ("_TZ3290_ixd9mvv4", "TS0049"), "LYAI-14", COUNTDOWN),
        "tuya_zcl",
    ),
    "datapoint_left_out_zbn_dj_63": (
        device(("Tuya", "ZBN-DJ-63"), ("_TZE204_lb0fsvba", "TS0601"), "ZBN-DJ-63", COUNTDOWN),
        "tuya_mcu",
    ),
    "datapoint_left_out_fk_bv05": (
        device(("FrankEver", "FK-BV05"), ("_TZE200_nbqnmkee", "TS0601"), "FK-BV05", COUNTDOWN),
        "tuya_mcu",
    ),
    # Multi-gang: its countdowns are per endpoint, so none is the device's.
    "datapoint_multi_gang": (
        device(("Zemismart", "ZMS-206EU-2"), ("_TZE204_3ctwoaip", "TS0601"), "ZMS-206EU-2", NO_COUNTDOWN),
        "tuya_mcu",
    ),
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
    # Other brands' standard lights (zigbee/standard_lights.py): by the definition model alone, after every family's
    # rules, so `other` until bridge/devices lists the definition. A member; a split-off, which stays in `other`; a
    # definition with turnsOffAtBrightness1, no member; a family's light whose definition is a member, which its family
    # keeps (`aqara_listed`'s T2_E27 is one too); and a Tuya light under a member's definition, which Tuya's rules keep.
    "standard_light": (
        listed(("OSRAM", "4058075816718"), ("OSRAM", "Outdoor Lantern W RGBW OSRAM")),
        "standard_light",
    ),
    "standard_light_before": (device(("OSRAM", "4058075816718")), "other"),
    "standard_light_excluded": (listed(("Paulmann", "924.70"), ("Paulmann Licht GmbH", "RGBW")), "other"),
    "standard_light_turns_off_at_1": (listed(("Innr", "RB 285 C"), ("innr", "RB 285 C")), "other"),
    "standard_light_in_a_family": (listed(("Sengled", "E11-G13"), ("sengled", "E11-G13")), "sengled"),
    "standard_light_tuya_inside": (listed(("Lidl", "14147206L"), (TUYA, "TS0505A")), "tuya_zcl"),
}


@pytest.mark.parametrize("name", DEVICES)
def test_each_listed_device_keeps_its_class(name):
    (registry, bridge), expected = DEVICES[name]

    assert device_class(registry, bridge) == expected


def test_the_snapshot_lists_every_class():
    assert {expected for _, expected in DEVICES.values()} == INTEGRATION.classes.keys()
