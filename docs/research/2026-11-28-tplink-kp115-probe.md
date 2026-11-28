# TP-Link KP115 countdown probe (2026-11-28)

Run date: 2026-11-28, 11:47 to 12:27 UTC (the plug's time zone, GB, is UTC in November). Runs the probes in
section 9 of [2026-11-28-tplink-call-patterns.md](2026-11-28-tplink-call-patterns.md) on one IOT plug; the KP105 that
section planned for died before the run. Nothing was plugged into the plug.

- **Device**: KP115(UK), hardware 1.0, firmware 1.0.20 Build 221125 Rel.092759, local protocol on port 9999, cloud
  connected.
- **Client**: python-kasa 0.13.0 (the version core pins), run as `uvx --from python-kasa kasa`, not core. `$HOST` is
  the plug's LAN address.
- **Starting state**: off, `count_down` rule list empty. Every probe ended with `delete_all_rules` and the plug off.

Raw replies are as printed. From `sys_info` I removed `deviceId`, `hwId`, `oemId`, `mac`, `alias`,
`latitude_i` and `longitude_i`, and printed only the countdown-related fields after the first read. The alias in
`kasa on`/`off` output is `<alias>`. Rule ids are the device's random per-rule ids. The times are the client's
UTC time when the reply arrived.

## Results

| Probe | Result | Decision |
|---|---|---|
| 1. Namespace and read shape | `count_down` answers; `countdown` is `-1 "module not support"`. A rule reads `{id, name, enable, delay, act, remain}`, `remain` in whole seconds | The IOT namespace is `count_down`. `get_attributes` `timer` reads `remain`, so IOT countdowns aren't refused. python-kasa's namespace is wrong for this plug (Finding) |
| 2. Add, replace, delete | `add_rule` returns `{"id"}`; a second is `-10 "table is full"`; `delete_all_rules` empties the list; a new `add_rule` then works | Send `delete_all_rules`, then `add_rule`. No `edit_rule` needed |
| 3. Manual switch | Button off cancels a running off rule (`enable: 0`, `delay: 0`, `remain: 0`); button on doesn't restore it; the plug stayed on past the fire time. `set_relay_state` (python-kasa `off`, `on`) does the same. A `set_relay_state` on to a plug already on leaves the rule running | No stale rule after a manual switch, so the Labs caveat doesn't apply. A plain off cancels the timer; a plain on that changes nothing leaves it |
| 4. Firing and residue | A 15 s off rule fired 15 to 16 s after it was added. The spent rule stays, disabled with `delay: 0`, `remain: 0`, and blocks the next `add_rule` with `-10` | DeviceSide deletes before every add. A rule is running when `enable` is 1, and `sys_info.active_mode` is `count_down` only while one runs |
| 5. Delay range | 86400 s accepted (`remain: 86399`); 86401 s, 604800 s and -1 s are `-3 "invalid argument"`. 0 s returns an `id` but stores the rule disabled, and it never fires. 1 s fires, about 3 s after the add | IOT `DurationLimits` is 1 s to 86400 s. A 0 s delay is a silent no-op on the device, so DeviceSide never sends it |

### `sys_info` while a rule runs

Section 2 of the research file doesn't name these. While a rule runs, `active_mode` is `"count_down"` and
`next_action` is `{"type": 2, "id": <rule id>, "schd_sec": <n>, "action": <act>}`; with none, `"none"` and
`{"type": -1}`. `schd_sec` is the fire time as seconds since local midnight: the 86400 s rule added at 12:03:45 read
43423, the same as a rule firing now. It carries no date, so `remain` is the time-left source, not `schd_sec`.

### Finding for python-kasa's maintainers

python-kasa's IOT `Countdown` module queries the namespace `countdown` (PK/kasa/iot/iotstrip.py#L121, #L352, at the pin
in the research file). This KP115 answers that namespace with `{"err_code": -1, "err_msg": "module not support"}` and
serves the countdown at `count_down`. The module is registered on strips and bulbs, not plugs, so this run doesn't
reach it directly; if strips name it as this plug does, the module is dropped on every device it is registered on.

## Probe commands and raw replies

### sys_info

```
kasa --host "$HOST" --type plug command --module system get_sysinfo
{"sw_ver":"1.0.20 Build 221125 Rel.092759","hw_ver":"1.0","model":"KP115(UK)","rssi":-50,"status":"new","obd_src":"tplink","mic_type":"IOT.SMARTPLUGSWITCH","feature":"TIM:ENE","updating":0,"led_off":0,"relay_state":0,"on_time":0,"icon_hash":"","dev_name":"Smart Wi-Fi Plug Mini","active_mode":"none","next_action":{"type":-1},"ntc_state":0}
```

### 1. Namespace and read shape

```
kasa --host "$HOST" --type plug command --module count_down get_rules
{"rule_list": []}
kasa --host "$HOST" --type plug command --module countdown get_rules
Error on countdown.get_rules: {'err_code': -1, 'err_msg': 'module not support'}
```

The rule's read shape, with `remain`, is in probe 2.

### 2. Add, replace, delete

```
11:50:52  kasa --host "$HOST" --type plug command --module system set_relay_state '{"state": 1}'
          {}
11:50:52  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":60,"act":0,"name":"t"}'
          {"id": "66E1F5387A61D9DE7A6D2AF27C6D3C01"}
11:50:53  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "66E1F5387A61D9DE7A6D2AF27C6D3C01", "name": "t", "enable": 1, "delay": 60, "act": 0, "remain": 59}]}
11:50:53  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "count_down", next_action {"type":2,"id":"66E1F5387A61D9DE7A6D2AF27C6D3C01","schd_sec":42711,"action":0}, on_time 1
11:50:59  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "66E1F5387A61D9DE7A6D2AF27C6D3C01", "name": "t", "enable": 1, "delay": 60, "act": 0, "remain": 53}]}
11:50:59  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":60,"act":0,"name":"t2"}'
          Error on count_down add_rule: {'err_code': -10, 'err_msg': 'table is full'}
11:51:00  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
11:51:00  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
11:51:00  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":60,"act":0,"name":"t"}'
          {"id": "4456D29065D30DE96752B1B667D01E8A"}
11:51:01  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "4456D29065D30DE96752B1B667D01E8A", "name": "t", "enable": 1, "delay": 60, "act": 0, "remain": 59}]}
11:51:01  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
11:51:02  kasa --host "$HOST" --type plug command --module system set_relay_state '{"state": 0}'
          {}
11:51:02  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
11:51:03  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

### 3. Manual switch during a countdown

A 300 s rule, not section 9's 120 s, to leave time for the button presses to be confirmed while it ran. The button
presses were made by hand at the plug, at the times logged.

```
11:54:09  kasa --host "$HOST" --type plug command --module system set_relay_state '{"state": 1}'
          {}
11:54:10  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":300,"act":0,"name":"t"}'
          {"id": "9D5622B08056BE8F805BA19386DBAF8C"}
11:54:10  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "9D5622B08056BE8F805BA19386DBAF8C", "name": "t", "enable": 1, "delay": 300, "act": 0, "remain": 300}]}
11:54:11  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "count_down", next_action {"type":2,"id":"9D5622B08056BE8F805BA19386DBAF8C","schd_sec":43149,"action":0}, on_time 2
11:54:28  # user reported button OFF
11:54:28  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "9D5622B08056BE8F805BA19386DBAF8C", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
11:54:29  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
11:54:56  # user reported button ON
11:54:57  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "9D5622B08056BE8F805BA19386DBAF8C", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
11:54:57  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "none", next_action {"type":-1}, on_time 18
11:59:49  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "9D5622B08056BE8F805BA19386DBAF8C", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
11:59:49  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "none", next_action {"type":-1}, on_time 310
11:59:50  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
```

Polls of `sys_info` every 10 s from the button on to 30 s past the fire time (11:59:10): 11:54:57 relay_state 1, active_mode none (last read 11:59:38). The plug
never turned off.

The HA side: python-kasa's `on` and `off` send `system.set_relay_state {"state": 1|0}` (PK/kasa/iot/iotplug.py#L75-L81),
the call core's switch sends. Then a plain `on` while already on, with a rule running.

```
11:59:50  kasa --host "$HOST" --type plug on
          Turning on <alias>
11:59:51  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":120,"act":0,"name":"t"}'
          {"id": "772FFA844620CBBC41A1D78D41264F11"}
11:59:51  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "772FFA844620CBBC41A1D78D41264F11", "name": "t", "enable": 1, "delay": 120, "act": 0, "remain": 119}]}
11:59:57  kasa --host "$HOST" --type plug off
          Turning off <alias>
11:59:57  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "772FFA844620CBBC41A1D78D41264F11", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
11:59:57  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
12:00:03  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:00:03  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "772FFA844620CBBC41A1D78D41264F11", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:00:04  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "none", next_action {"type":-1}, on_time 1
12:02:30  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "772FFA844620CBBC41A1D78D41264F11", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:02:30  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "none", next_action {"type":-1}, on_time 147
12:02:31  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:02:31  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":60,"act":0,"name":"t"}'
          {"id": "B9954A19AA9DE64AAE9ECF66AF1AD94F"}
12:02:35  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:02:35  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "B9954A19AA9DE64AAE9ECF66AF1AD94F", "name": "t", "enable": 1, "delay": 60, "act": 0, "remain": 56}]}
12:02:35  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 1, active_mode "count_down", next_action {"type":2,"id":"B9954A19AA9DE64AAE9ECF66AF1AD94F","schd_sec":43410,"action":0}, on_time 152
12:02:36  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:02:36  kasa --host "$HOST" --type plug off
          Turning off <alias>
12:02:37  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:02:37  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

Polls every 10 s from the second `on` to 30 s past the fire time (12:01:51): 12:00:04 relay_state 1, active_mode none (last read 12:02:19). The plug never turned off.

### 4. Firing and residue

```
12:02:49  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:02:50  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":15,"act":0,"name":"t"}'
          {"id": "83800E0BA9014F2AA98BDFEBAC8B3FFB"}
12:02:50  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "83800E0BA9014F2AA98BDFEBAC8B3FFB", "name": "t", "enable": 1, "delay": 15, "act": 0, "remain": 14}]}
12:03:15  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "83800E0BA9014F2AA98BDFEBAC8B3FFB", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:03:16  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
12:03:16  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":15,"act":1,"name":"t"}'
          Error on count_down add_rule: {'err_code': -10, 'err_msg': 'table is full'}
12:03:16  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "83800E0BA9014F2AA98BDFEBAC8B3FFB", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:03:42  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "83800E0BA9014F2AA98BDFEBAC8B3FFB", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:03:42  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
12:03:43  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:03:43  kasa --host "$HOST" --type plug off
          Turning off <alias>
12:03:43  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:03:44  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

Polls of `sys_info` every 1.4 s after the off rule was added at 12:02:50: 12:02:50 relay_state 1, active_mode count_down; 12:03:06 relay_state 0, active_mode none (last read 12:03:14). The relay went off between the
12:03:04 and 12:03:06 reads, 15 to 16 s after the add. After the rejected on rule: 12:03:17 relay_state 0, active_mode none (last read 12:03:40).

### 5. Long delay

```
12:03:44  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":86400,"act":1,"name":"t"}'
          {"id": "EADB206AEE58FE2FEFDC5C71EDDDF3D3"}
12:03:45  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "EADB206AEE58FE2FEFDC5C71EDDDF3D3", "name": "t", "enable": 1, "delay": 86400, "act": 1, "remain": 86399}]}
12:03:45  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "count_down", next_action {"type":2,"id":"EADB206AEE58FE2FEFDC5C71EDDDF3D3","schd_sec":43423,"action":1}, on_time 0
12:03:46  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:03:46  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:03:46  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":604800,"act":1,"name":"t"}'
          Error on count_down add_rule: {'err_code': -3, 'err_msg': 'invalid argument'}
12:03:47  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:03:47  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
12:03:48  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:03:48  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:03:49  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

Narrowing the maximum:

```
12:07:08  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":86401,"act":1,"name":"t"}'
          Error on count_down add_rule: {'err_code': -3, 'err_msg': 'invalid argument'}
12:07:08  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:07:09  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:07:09  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

### 5b. Minimum delay

Run at 12:26 to 12:27 UTC. `sys_info` polled every 0.9 s for 6 s after each add.

```
12:26:29  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:26:30  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":0,"act":0,"name":"t"}'
          {"id": "69E31F076FE376E66FE5060F6CE572FF"}
12:26:30  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "69E31F076FE376E66FE5060F6CE572FF", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:26:37  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "69E31F076FE376E66FE5060F6CE572FF", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:26:38  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:26:38  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:26:39  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":1,"act":0,"name":"t"}'
          {"id": "470F4D506482FDC1620135F16387AD39"}
12:26:39  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "470F4D506482FDC1620135F16387AD39", "name": "t", "enable": 1, "delay": 1, "act": 0, "remain": 1}]}
12:26:46  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": [{"id": "470F4D506482FDC1620135F16387AD39", "name": "t", "enable": 0, "delay": 0, "act": 0, "remain": 0}]}
12:26:47  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:26:47  kasa --host "$HOST" --type plug on
          Turning on <alias>
12:26:47  kasa --host "$HOST" --type plug command --module count_down add_rule '{"enable":1,"delay":-1,"act":0,"name":"t"}'
          Error on count_down add_rule: {'err_code': -3, 'err_msg': 'invalid argument'}
12:26:48  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:26:54  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:26:55  kasa --host "$HOST" --type plug command --module count_down delete_all_rules
          {}
12:26:55  kasa --host "$HOST" --type plug off
          Turning off <alias>
12:26:56  kasa --host "$HOST" --type plug command --module count_down get_rules
          {"rule_list": []}
12:26:56  kasa --host "$HOST" --type plug command --module system get_sysinfo
          # relay_state 0, active_mode "none", next_action {"type":-1}, on_time 0
```

Polls: delay 0: 12:26:31 relay_state 1, active_mode none (last read 12:26:36); delay 1: 12:26:40 relay_state 1, active_mode count_down; 12:26:42 relay_state 0, active_mode none; delay -1: 12:26:48 relay_state 1, active_mode none (last read 12:26:53).
The 1 s rule turned the relay off between the 12:26:42.0 and 12:26:42.9 reads, about 3 s after the add at 12:26:39.

## Left open

- Strip outlets (`context.child_ids`), wall switches and IOT bulbs weren't probed; nor whether the rule survives a
  power cut or reboot.
