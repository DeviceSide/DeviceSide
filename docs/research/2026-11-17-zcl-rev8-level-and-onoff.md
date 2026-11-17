# ZCL Rev 8: Level Control and On/Off, mandatory vs optional (2026-11-17)

Question: which Level Control and On/Off commands and attributes does the Zigbee Cluster Library mark mandatory (M) or
optional (O), what does Level Control's Options/ExecuteIfOff do, and how do Level Control commands treat OnOff? This is
the evidence behind the `other` trial on `raise_brightness`, `lower_brightness` and `stop` in
[`docs/internals.md`](../internals.md) (Zigbee 3.0 certification entry) and behind `other` not being built on
`turn_on_for` ([timed-on call patterns](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)).

Marks: **[V]** verified in the PDF's text extract (`pdftotext -layout`). **[GAP]** not in this document. Section and
table numbers are the document's; quotes are short.

## Source

Zigbee Cluster Library Specification, Document 07-5123 Revision 8, © 2007-2020 Zigbee Alliance (now CSA).
`https://csa-iot.org/wp-content/uploads/2022/01/07-5123-08-Zigbee-Cluster-Library-1.pdf`. csa-iot.org serves it to a
browser but blocks scripted fetches (Cloudflare check), so it was saved by hand on 2026-11-17. The PDF is copyrighted
and not kept in the repo.

## 1. Level Control commands received (§3.10.2.3, Table 3-59) [V]

| ID | Command | M/O |
|---|---|---|
| 0x00 | Move to Level | M |
| 0x01 | Move | M |
| 0x02 | Step | M |
| 0x03 | Stop | M |
| 0x04 | Move to Level (with On/Off) | M |
| 0x05 | Move (with On/Off) | M |
| 0x06 | Step (with On/Off) | M |
| 0x07 | Stop | M |
| 0x08 | Move to Closest Frequency | M: CurrentFrequency attribute supported |

The derived Level Control for Lighting cluster (§3.19, same cluster ID 0x0008; the base cluster's note says lights use
it) lists 0x00-0x07 as M in its own table (Table 3-145 in the extract, titled "Pulse Width Modulation" by mistake in
the document). [V]

## 2. Level Control attributes (§3.10.2.2, Table 3-56) [V]

| ID | Attribute | M/O |
|---|---|---|
| 0x0000 | CurrentLevel | M |
| 0x000F | Options (map8, RW, default 0) | **O** |
| 0x0010 | OnOffTransitionTime | O |
| 0x0011 | OnLevel | O |
| 0x0012 | OnTransitionTime | O |
| 0x0013 | OffTransitionTime | O |
| 0x4000 | StartUpCurrentLevel | O |

Options, Table 3-57 (§3.10.2.2.8): bit 0 is ExecuteIfOff ("0 – Do not execute command if OnOff is 0x00 (FALSE)", "1 –
Execute command if OnOff is 0x00"); bit 1 is reserved for derived clusters (Level Control for Lighting).
§3.10.2.2.8.1: "Command execution SHALL NOT continue beyond the Options processing if all of these criteria are true":

- the command is one of the "without On/Off" commands: Move, Move to Level, Stop, or Step;
- the On/Off cluster exists on the same endpoint;
- the OnOff attribute there is 0x00 (FALSE);
- the ExecuteIfOff bit is 0.

The temporary Options bitmap is built from the attribute plus the command's OptionsMask and OptionsOverride fields
(§3.10.2.3.1.2), which Rev 8 makes mandatory fields of Move to Level (CCB 2814). So a "without On/Off" command to an
off light does nothing unless the attribute's ExecuteIfOff is 1 or the command's mask and override set it. [V]

**Derived cluster differs.** In Level Control for Lighting (§3.19.2.2, Table 3-143) Options is **M** (the base
cluster's O does not carry over); OnOffTransitionTime, OnLevel, OnTransitionTime, OffTransitionTime,
DefaultMoveRate and StartUpCurrentLevel stay O. §3.19.2.2.3 (Table 3-144) adds bit 1, CoupleColorTempToLevel. [V]

## 3. Effect of Level Control commands on OnOff (§3.10.2.1.2) [V]

Two command sets, "identical, except that the first set (Move to Level, Move and Step) SHALL NOT affect the OnOff
attribute, whereas the second set ('with On/Off' variants) SHALL." The first set keeps CurrentLevel and OnOff
independent ("a 'turn to set level and press to turn on/off' light dimmer"). The second links them: "When the level is
reduced to its minimum the OnOff attribute is automatically turned to Off, and when the level is increased above its
minimum the OnOff attribute is automatically turned to On."

So a Move or Move to Level without On/Off, sent to a light that is off, leaves it off (and, with ExecuteIfOff 0, is not
executed at all, per section 2); the With On/Off forms turn it on once the level is above minimum. §3.10.2.1.3: a
With On/Off command that changes OnOff also updates GlobalSceneControl per §3.8.2.2.2. Separately, §3.10.2.1.1 /
Table 3-55: On/Off commands act on CurrentLevel (stored level, OnLevel, OnOffTransitionTime). [V]

## 4. On/Off commands received (§3.8.2.3, Table 3-47) [V]

| ID | Command | M/O |
|---|---|---|
| 0x00 | Off | M |
| 0x01 | On | M |
| 0x02 | Toggle | M |
| 0x40 | Off with effect | O |
| 0x41 | On with recall global scene | O |
| 0x42 | On with timed off | O |

On With Timed Off (§3.8.2.3.6) payload, Figure 3-37: On/Off Control (uint8), On Time (uint16), Off Wait Time (uint16).
On/Off Control bit 0 is Accept Only When On (bits 1-7 reserved): when 1, "the On With Timed Off command SHALL only be
accepted if the OnOff attribute is equal to 0x01"; when 0, it "SHALL be processed unconditionally". On Time and Off
Wait Time are in 1/10 s, range 0x0000 to 0xfffe. [V]

## 5. On/Off attributes (§3.8.2.2, Table 3-45) [V]

| ID | Attribute | M/O |
|---|---|---|
| 0x0000 | OnOff | M |
| 0x4000 | GlobalSceneControl | O |
| 0x4001 | OnTime | O |
| 0x4002 | OffWaitTime | O |
| 0x4003 | StartUpOnOff | O |

## 6. Color Control Options (§5.2.2.2.1.10, Table 5.6) [V]

The "Options map8 ... M" row belongs to Color Control (0x0300), Table 5.3 (Color Information attribute set): ID
0x000F, RW, default 0x00, **M**. Bit 0 is ExecuteIfOff ("0 – Do not execute command if the On/Off cluster, OnOff
attribute is 0x00"). Its rule has three criteria, the same as Level Control's minus the command-list criterion: the
On/Off cluster is on the same endpoint, OnOff is 0x00, and the bit is 0. So the bit means the same, and the text doesn't
restrict it to a named command subset. Color Control's Options is mandatory, Level Control's base Options optional.

## What this document doesn't settle

- Whether Zigbee 3.0 or the Lighting & Occupancy Device Specification (15-0014) makes On With Timed Off mandatory for
  lights: not in this document. [GAP]
- Which Level Control cluster a given light implements (base or Level Control for Lighting): device dependent. The
  document says only that lights use the derived one. [GAP]
- How a device's firmware actually behaves: the spec marks only what a conforming server must accept.

## Bottom line for DeviceSide

1. Level Control's fade and stop commands, 0x00-0x07, are all M (section 1): the basis of `other`'s trial on
   `raise_brightness`, `lower_brightness` and `stop` in [`docs/internals.md`](../internals.md).
2. On With Timed Off (0x42), OnTime and OffWaitTime are O (sections 4 and 5), consistent with `other` not built on
   `turn_on_for` ([timed-on call patterns](../integrations/zigbee2mqtt/research/2026-11-14-timed-on-call-patterns.md)).
3. Level Control's Options (and so ExecuteIfOff) is O in the base cluster (section 2), but Level Control for
   Lighting, which lights use, marks it M, as Color Control does (section 6), and a command's OptionsMask and
   OptionsOverride set ExecuteIfOff for that command alone (section 2). So this document gives no reason a certified
   light refuses a write while off; `other` is not built on `set_attributes` for its known departures (Hue, Sengled,
   Gledopto), not for the base cluster's O. Whether a given firmware honors ExecuteIfOff is a device fact the spec
   doesn't prove.
