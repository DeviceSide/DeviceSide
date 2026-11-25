// Resolves every zigbee-herdsman-converters (ZHC) light definition the way Zigbee2MQTT does, and prints its traits as
// JSON for scripts/zhc_table.py, which decides membership. Usage: node resolve.mjs <built ZHC checkout>.
//
// Each definition goes through ZHC's own prepareDefinition, which applies every extend and prepends the generic
// converters, so toZigbee and meta are what Zigbee2MQTT runs (docs/research/2026-11-25-z2m-converter-survey.md, Part A).
// A light is a definition whose resolved exposes hold a `light`. For each key DeviceSide publishes, the converter
// Zigbee2MQTT picks (the first whose key list holds it) is compared with ZHC's standard one.

import {createRequire} from "node:module";
import path from "node:path";

const root = path.resolve(process.argv[2]);
const require = createRequire(path.join(root, "package.json"));
const zhc = require(path.join(root, "dist/index.js"));
const tz = require(path.join(root, "dist/converters/toZigbee.js"));
const devices = require(path.join(root, "dist/devices/index.js"));

// The keys DeviceSide publishes to a light's set topic, each with ZHC's standard converters for it. `state` on a light
// with brightness must go to the brightness converter: `on_off` there would send a plain On beside the level, the
// departure ZHC fixed on Inovelli and Legrand (survey, Part 2a); on an on/off light, `on_off` is the standard one.
const STANDARD = {
    state: [tz.light_onoff_brightness],
    brightness: [tz.light_onoff_brightness],
    transition: [tz.ignore_transition],
    color: [tz.light_color, tz.light_color_colortemp],
    hue_move: [tz.light_hue_saturation_move],
    brightness_move: [tz.light_brightness_move],
    command: [tz.command],
    read: [tz.read],
};
const ON_OFF_ONLY = [tz.on_off, tz.light_onoff_brightness];

function exposesOf(definition) {
    const exposes = definition.exposes;
    if (Array.isArray(exposes)) return exposes;
    try {
        return exposes({isDummyDevice: true}, {});
    } catch {
        return [];
    }
}

function features(expose) {
    return [expose, ...(expose.features ?? []).flatMap(features)];
}

function converterFor(definition, key) {
    return definition.toZigbee.find((c) => c.key?.includes(key));
}

// Whether a converter is one of the standard ones, by identity or by its convertSet (an extend's copy).
function isStandard(converter, standards) {
    return standards.some((s) => converter === s || converter.convertSet === s.convertSet);
}

// The keys whose converter isn't a standard one; a key with no converter isn't one the light takes.
function overrides(definition) {
    const dimmable = converterFor(definition, "brightness") !== undefined;
    const found = [];
    for (const [key, standards] of Object.entries(STANDARD)) {
        const converter = converterFor(definition, key);
        const allowed = key === "state" && !dimmable ? ON_OFF_ONLY : standards;
        if (converter && !isStandard(converter, allowed)) found.push(key);
    }
    return found;
}

// Meta values as JSON: a flag's value, or its type where it is a function or object.
function metaOf(definition) {
    const meta = {};
    for (const [key, value] of Object.entries(definition.meta ?? {})) {
        meta[key] = ["boolean", "number", "string"].includes(typeof value) ? value : typeof value;
    }
    return meta;
}

// Every model string a definition can be published under: its own, and each white label's.
function modelsOf(definition) {
    return [definition.model, ...(definition.whiteLabel ?? []).map((w) => w.model)];
}

const all = devices.default ?? devices.definitions ?? devices;
const rows = [];
const others = new Set();
for (const original of all) {
    const definition = zhc.prepareDefinition(original);
    const exposes = exposesOf(definition);
    const lights = exposes.filter((e) => e.type === "light");
    if (lights.length === 0) {
        for (const model of modelsOf(original)) others.add(model);
        continue;
    }
    rows.push({
        model: definition.model,
        vendor: definition.vendor,
        zigbee_models: original.zigbeeModel ?? [],
        fingerprinted: Boolean(original.fingerprint?.length),
        fingerprint_manufacturers: [...new Set((original.fingerprint ?? []).map((f) => f.manufacturerName).filter(Boolean))],
        white_labels: (original.whiteLabel ?? []).map((w) => ({
            model: w.model,
            vendor: w.vendor ?? definition.vendor,
            fingerprinted: "fingerprint" in w && Boolean(w.fingerprint?.length),
        })),
        meta: metaOf(definition),
        overrides: overrides(definition),
        color_hs: lights.some((light) => features(light).some((f) => f.name === "color_hs")),
        // The device-wide exposes' properties, as DeviceSide's rules read them (rules.py, definition_fields).
        exposes: exposes.filter((e) => e.endpoint === undefined && e.property).map((e) => e.property),
    });
}
process.stdout.write(JSON.stringify({definitions: all.length, lights: rows, other_models: [...others].sort()}));
