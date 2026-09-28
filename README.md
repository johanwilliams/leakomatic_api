# Leakomatic for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/johanwilliams/leakomatic_api)](https://github.com/johanwilliams/leakomatic_api/releases)
[![Tests](https://github.com/johanwilliams/leakomatic_api/actions/workflows/tests.yml/badge.svg)](https://github.com/johanwilliams/leakomatic_api/actions/workflows/tests.yml)
[![Validate](https://github.com/johanwilliams/leakomatic_api/actions/workflows/validate.yml/badge.svg)](https://github.com/johanwilliams/leakomatic_api/actions/workflows/validate.yml)

Monitor and control your [Leakomatic](https://www.leakomatic.com) water leak guard from Home Assistant: see whether water is flowing, whether the valve is open, and the state of the device's three leak tests, get alarms as they happen, and switch between Home, Away and Pause.

The integration connects to the Leakomatic cloud with your Leakomatic account and receives updates in real time. It is a community project, not affiliated with Leakomatic.

- [What you need](#what-you-need)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Examples](#examples)
- [How data is updated](#how-data-is-updated)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Removal](#removal)
- [Contributing](#contributing)

## What you need

- A Leakomatic device connected to the Leakomatic cloud, and the email and password you use in Leakomatic's app or at [cloud.leakomatic.com](https://cloud.leakomatic.com).
- Home Assistant 2024.8 or newer (tested with 2026.9).

All devices on the account are added. Temperature, pressure and water volume need an accessory on the device (see [Entities](#entities)).

## Installation

### With HACS (recommended)

1. In HACS, open the menu (⋮) → **Custom repositories**, add `https://github.com/johanwilliams/leakomatic_api` with the type **Integration**.
2. Search for **Leakomatic** in HACS and download it.
3. Restart Home Assistant.

### Manually

1. Copy `custom_components/leakomatic` from the latest [release](https://github.com/johanwilliams/leakomatic_api/releases) into the `custom_components` folder of your Home Assistant configuration.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add integration** and search for **Leakomatic**.
2. Enter your Leakomatic email and password.

One entry is created per Leakomatic account, named after the email, with one device per Leakomatic device on the account. Adding the same account twice is refused. A device added to or removed from the account shows up or disappears the next time Home Assistant restarts or the integration is reloaded.

If you change your Leakomatic password, Home Assistant shows a notification asking for the new one.

## Entities

Each Leakomatic device gets the entities below. The names are shown in English or Swedish, following your Home Assistant language.

### Water and valve

| Entity | Type | What it shows |
|---|---|---|
| Flow indicator | Binary sensor | On while water is flowing. Unknown after startup until the first flow. |
| Valve | Binary sensor | On when the valve is open, off when it is closed. |
| Last flow duration | Sensor (s) | How long the last completed flow lasted. |
| Longest tightness period | Sensor (s) | The longest period without any flow. |
| Quick test index | Sensor | The current quick test index. |
| Total volume | Sensor (m³) | The reading of a water meter on the device's pulse input. Usable as a water source in the Energy dashboard. *Disabled by default.* |
| Temperature, Pressure | Sensor (°C, bar) | Readings from a sensor on the device's analog input. Unknown when the sensor is not connected. *Disabled by default.* |

Total volume, temperature and pressure need an accessory connected and set up in Leakomatic's app (a water meter on "AUX In", a sensor on "Analog In"). They follow the data Leakomatic sends but have not been tested with real accessories; reports are welcome.

### Leak tests

| Entity | What it watches |
|---|---|
| Flow test | Water flowing longer than allowed: one limit when you are home, a much shorter one when you are away. |
| Quick test | Small, frequent pulses over the last hour, such as a dripping tap or a running toilet. |
| Tightness test | That the water has been completely still for a while every day; a hidden leak prevents that. |

Each test sensor is `clear`, `warning` or `alarm` (shown translated in the UI), or unknown if Leakomatic reports a level the integration does not recognise. Its attributes show the test's settings from Leakomatic's app, for example the flow test's alarm delay; they follow changes you make in the app.

### Mode and control

| Entity | Type | What it does |
|---|---|---|
| Mode | Select | Home, Away or Pause. Changing it changes the device's mode. |
| Pause ends | Sensor (timestamp) | When the pause ends and the device returns to its previous mode. Unknown when not paused. The pause length is set in Leakomatic's app. |
| Reset alarms | Button | Resets all warnings and alarms on the device. |

If Leakomatic does not accept a mode change or an alarm reset, the action fails with an error: the UI shows it, and an automation stops at that step with the error in its trace.

### Connection (diagnostic)

| Entity | What it shows |
|---|---|
| Online status | Whether the device is online. Off when Leakomatic reports it offline, or when nothing has been heard from it for 15 minutes (it reports every 5 minutes). Attribute `last_seen`. |
| WebSocket connectivity | Whether the real-time connection to Leakomatic is up. Attribute `reconnection_phase`. |
| Signal strength | The device's Wi-Fi signal (dBm). |

## Examples

Replace the entity IDs with yours: open **Settings → Devices & services → Leakomatic** and select the device. The examples use the automation syntax of Home Assistant 2024.10 and later (`triggers:`, `actions:`).

### Away mode when the house is empty, home mode when someone is back

In away mode the flow test allows only a very short flow, so a leak is caught within seconds when nobody is there to notice it. This automation switches to away when the alarm is armed away or everyone has left, and back to home when the alarm is disarmed or someone comes home:

```yaml
automation:
  - alias: Leak guard follows the house
    mode: queued
    triggers:
      - trigger: state
        entity_id: alarm_control_panel.house
        to: armed_away
        id: away
      - trigger: state
        entity_id: zone.home
        to: "0"
        id: away
      - trigger: state
        entity_id: alarm_control_panel.house
        to: disarmed
        id: home
      - trigger: numeric_state
        entity_id: zone.home
        above: 0
        id: home
    conditions:
      # Leave a pause (for example during irrigation) alone
      - condition: not
        conditions:
          - condition: state
            entity_id: select.leakomatic_mode
            state: pause
    actions:
      - action: select.select_option
        target:
          entity_id: select.leakomatic_mode
        data:
          option: "{{ trigger.id }}"
```

### Pause during irrigation

Watering the lawn can run longer than the flow test allows in home mode (20 minutes by default), which would raise a flow alarm. Pause the leak guard just before the irrigation starts and switch back to home when it is done:

```yaml
automation:
  - alias: Leak guard paused during irrigation
    mode: restart
    triggers:
      - trigger: state
        entity_id: switch.irrigation
        to: "on"
        id: start
      - trigger: state
        entity_id: switch.irrigation
        to: "off"
        id: done
    actions:
      - choose:
          - conditions:
              - condition: trigger
                id: start
            sequence:
              - action: select.select_option
                target:
                  entity_id: select.leakomatic_mode
                data:
                  option: pause
          - conditions:
              - condition: trigger
                id: done
            sequence:
              - action: select.select_option
                target:
                  entity_id: select.leakomatic_mode
                data:
                  option: home
```

If the irrigation is started by a schedule, trigger the pause a minute before it instead. The pause ends by itself after the time set in Leakomatic's app (*Time in pause mode*); make it longer than the longest irrigation, or the device goes back to its previous mode while the water is still running. The *Pause ends* sensor shows when that happens.

### Notify on a leak alarm

```yaml
automation:
  - alias: Leak alarm
    triggers:
      - trigger: state
        entity_id:
          - sensor.leakomatic_flow_test
          - sensor.leakomatic_quick_test
          - sensor.leakomatic_tightness_test
        to:
          - warning
          - alarm
    actions:
      - action: notify.notify
        data:
          title: Leakomatic
          message: "{{ trigger.to_state.name }}: {{ trigger.to_state.state }}"
```

### Remind before the pause ends

```yaml
automation:
  - alias: Leak guard pause ends soon
    triggers:
      - trigger: time
        at:
          entity_id: sensor.leakomatic_pause_ends
          offset: "-00:10:00"
    actions:
      - action: notify.notify
        data:
          message: The leak guard resumes monitoring in 10 minutes.
```

### How long has water been flowing this hour, and today?

Home Assistant's **History stats** helper counts how long the flow indicator has been on. Measured over a week, this matches the flow durations the device reports to within seconds. Create it under Settings → Devices & services → Helpers → Create helper → History stats, or in YAML:

```yaml
sensor:
  - platform: history_stats
    name: Water flow this hour
    entity_id: binary_sensor.leakomatic_flow_indicator
    state: "on"
    type: time
    start: "{{ now().replace(minute=0, second=0, microsecond=0) }}"
    end: "{{ now() }}"

  - platform: history_stats
    name: Water flow today
    entity_id: binary_sensor.leakomatic_flow_indicator
    state: "on"
    type: time
    start: "{{ today_at() }}"
    end: "{{ now() }}"
```

The sensors show hours (0.25 = 15 minutes). A flow that crosses the hour is split correctly between the hours. Time while the flow indicator is unknown after a restart is not counted.

## How data is updated

The integration logs in to the Leakomatic cloud, reads each device's data once at startup, and then receives every change in real time over a websocket: flows, test results, alarms, mode changes and status messages. It does not poll.

- The device itself reports about every 5 minutes; flows and alarms are sent as they happen.
- Leakomatic closes the websocket on a schedule, typically once a night. The integration reconnects within seconds; you will not see it.
- If the connection is lost, the integration retries: quickly at first, then every 6 hours, then every 12 hours, without giving up. If the connection has been down for **5 minutes**, all entities except WebSocket connectivity become unavailable, so old values are never shown as current.
- An expired Leakomatic login is renewed automatically.

## Known limitations

- **No official API.** The integration uses the same cloud service as Leakomatic's web page and app. A change on Leakomatic's side can break it until the integration is updated.
- **The valve cannot be controlled.** Leakomatic's cloud offers no command to open or close it; the device closes it itself on an alarm, according to its settings.
- **No configuration changes.** Test limits, pause length and other settings are changed in Leakomatic's app; the integration shows them.
- **Accessories untested.** Total volume, temperature and pressure have not been tested with real accessories.
- **Several devices** on one account are supported but only tested with one.

## Troubleshooting

1. **Download the diagnostics:** Settings → Devices & services → Leakomatic, menu (⋮) → *Download diagnostics* (or from a device page). The file contains the device data and the connection state; email, serial numbers, IP address, location and account IDs are removed, and the alarm and event history is left out, so it can be attached to a GitHub issue.
2. **Turn on debug logging** without a restart: call the `logger.set_level` action with `custom_components.leakomatic: debug` (and `warning` to turn it off again). The log is under Settings → System → Logs.

Common situations:

| You see | What it means |
|---|---|
| "Retrying setup" under Devices & services | Leakomatic could not be reached at startup. Home Assistant keeps trying; check the network if it does not recover. |
| A notification asking for the password | Leakomatic rejected the stored password. Enter the current one; the integration reloads by itself. |
| All entities unavailable | No connection to Leakomatic for more than 5 minutes. The log says `No connection to Leakomatic for 5 minutes, marking entities unavailable`, and `Connection to Leakomatic restored` when it is back. |
| Warning `WebSocket reconnection failed 10 times, retrying every 6 hours (phase 2)` | The quick reconnection attempts failed. Check the network and whether Leakomatic's service works. |
| Online status off, log `Nothing heard from the device for 15 minutes` | The connection to Leakomatic works, but the device has stopped reporting. Check its power and network. |

## Removal

1. Go to **Settings → Devices & services → Leakomatic**, open the menu (⋮) on the entry and choose **Delete**.
2. Remove the integration in HACS, or delete `custom_components/leakomatic` if you installed it manually.
3. Restart Home Assistant.

Removing the integration changes nothing on the Leakomatic device or in your Leakomatic account.

## Contributing

Contributions are welcome. For larger changes, please open an issue first. See the [changelog](CHANGELOG.md) for what has changed between versions.

The tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component). They need Python 3.14 on Linux or macOS (Home Assistant does not run on Windows; use WSL or a container):

```bash
pip install -r requirements_test.txt
python -m pytest
pip install ruff
ruff check .
```

Every pull request is checked by the tests, [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/), the [HACS action](https://hacs.xyz/docs/publish/action) and [Ruff](https://docs.astral.sh/ruff/). Test data must be invented: never add payloads from a real account, since they contain serial numbers, user IDs and locations.

## License

MIT, see [LICENSE](LICENSE).
