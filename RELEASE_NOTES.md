# Release Notes - Version 0.2.0

A large reliability release. The integration now recovers by itself when Leakomatic's cloud or the login session fails, shows when it does not know something instead of guessing, and is covered by tests and Home Assistant's own validation. The complete list of changes is in the [changelog](CHANGELOG.md).

## Before you upgrade

These changes can affect your automations and dashboards:

- **The `leakomatic.change_mode` action is removed.** Use `select.select_option` on the device's Mode entity instead:

  ```yaml
  action: select.select_option
  target:
    entity_id: select.leakomatic_mode
  data:
    option: pause   # home, away or pause
  ```

- **Unknown instead of a guess.** After a restart, *Flow indicator* and *Online status* are unknown until the first message from the device (previously off). *Valve* is unknown if its state is missing (previously closed). An automation that triggers on these turning off may no longer fire at startup.
- **Unavailable when the connection is lost.** If the connection to Leakomatic has been down for 5 minutes, all entities except *WebSocket connectivity* become unavailable, instead of showing old values as current. Short disconnects, such as Leakomatic's nightly one, are not visible.
- **A failed mode change or alarm reset now raises an error**, so an automation stops at that step instead of carrying on as if it had worked.
- **The config entry is renamed** to your Leakomatic email at the first start (unless you renamed it yourself).
- **Total volume** (only with a water meter connected) showed a thousandth of the real value. After the update it jumps to the correct reading, which the long-term statistics count as consumption once; correct it under Developer tools → Statistics.
- Home Assistant **2024.8** or newer is required.

## Highlights

- **Recovers by itself:** retries the setup when Leakomatic cannot be reached, renews an expired login, asks for a new password when the old one is rejected, and reconnects the real-time connection without manual reloads.
- **New sensor *Pause ends*:** when the pause mode ends.
- **Online status** turns off when the device has not reported for 15 minutes, and when Leakomatic reports it offline (which previously set it *online*).
- **Leak test sensors** keep their settings as attributes (they disappeared after the first alarm), follow setting changes made in Leakomatic's app, show every active alarm at startup, and are enum sensors with `clear`, `warning` and `alarm`.
- **Each message handled once:** Leakomatic sends every message twice; the copy is now dropped.
- **Diagnostics** you can download and attach to an issue, with personal data removed.
- **Translations:** attribute names, error messages and the WebSocket connectivity name are now translated (English and Swedish).
- **A new README** with the entities in tables and automation examples.
- Validated by hassfest and the HACS action, with 115 tests.

## Installation

1. Update through HACS, or copy `custom_components/leakomatic` from this release into your Home Assistant configuration.
2. Restart Home Assistant.

Thanks to @skallan for the reconnection fixes in 0.1.6 that this release builds on.
