"""The standard lights table (zigbee/standard_lights.py): which ZHC definitions it holds, with the Zigbee strings ZHC
matches them on, and which it splits off. scripts/zhc_table.py generates and checks it
(tests/scripts/test_zhc_table.py); Zigbee2MQTT's class on it: tests/integrations/zigbee2mqtt/test_standard_lights.py."""

import pytest

from custom_components.deviceside.zigbee.standard_lights import EXCLUDED, MODELS, Light, members


def test_the_members_hold_the_survey_s_examples():
    assert MODELS["4058075816718"] == Light("OSRAM", True, ("Outdoor Lantern W RGBW OSRAM",), ())
    assert MODELS["4058075168572"] == Light("LEDVANCE", False, ("Tibea TW Z3",), ())


@pytest.mark.parametrize(
    "model",
    [
        # omitOptionalLevelAndColorParams: the option fields rejected (survey, Part 4).
        "NLG-CCT light",
        "100.110.51",
        "Ribag Air O",
        "WDE002386",
        # turnsOffAtBrightness1: #613 owns the floor.
        "RB 285 C",
        # A converter of their own for a key DeviceSide sends (survey, Part 1c).
        "DD10Z",
        "VB-FTW-A19",
        "VB-RGBTW-A19",
        "VZM30-SN",
        "VZM31-SN",
        "VZM32-SN",
        "VZM36",
        "067797",
        "4256050-ZHAC",
        "4257050-ZHAC",
        "CTM_MBD_Dim",
        "TI0001-dimmer",
        "SAV-DL6IN-24V-12W",
        "EBF_RGB_Zm",
    ],
)
def test_a_flagged_or_overridden_definition_is_no_member(model):
    assert model not in MODELS
    assert model not in members()


def test_every_split_off_is_out_of_the_class():
    """Step 3's split-offs (survey, Part 4's rows no flag catches) are in MODELS, and out of the class."""
    excluded = {row.model for row in EXCLUDED}
    assert excluded <= MODELS.keys()
    assert not excluded & members()
    assert {"FLS-PP", "924.70", "404036/45327/45317/45328", "404065", "900024/12253", "5120.1100"} <= excluded


def test_a_fingerprinted_white_label_carries_its_own_fingerprint():
    """Immax's 07743L is a white label Zigbee2MQTT names by its fingerprint alone."""
    assert MODELS["07743L"] == Light("Immax", False, (), (("TS0505B", "_TZ3210_pwauw3g2"),))


def test_every_row_has_its_zigbee_strings_in_shape():
    for model, row in MODELS.items():
        assert isinstance(row, Light), model
        assert all(isinstance(zigbee_model, str) for zigbee_model in row.zigbee_models), model
        assert all(len(pair) == 2 and all(isinstance(s, str) for s in pair) for pair in row.fingerprints), model
