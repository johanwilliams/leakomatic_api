# Changelog

All notable changes to the Leakomatic Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-28

### Removed
- **Breaking:** the `leakomatic.change_mode` action (service) is removed. Use the `select.select_option` action on the device's Mode entity instead, which does the same and reports errors:

  ```yaml
  action: select.select_option
  target:
    entity_id: select.leakomatic_mode
  data:
    option: pause   # home, away or pause
  ```

  The removed action also used the wrong account when several Leakomatic accounts were configured, was never removed when the integration was unloaded, and reported success even when the mode change failed.

### Fixed
- Several devices on one account: if one device's data could not be fetched at startup, that device was left out until the next reload; now the whole setup is retried. A device removed from the Leakomatic account is removed from Home Assistant at the next startup instead of staying behind.
- If receiving from the websocket failed with an unexpected error that did not close the connection, the receive loop retried at once without pause, logging errors thousands of times per second. Such an error now ends the connection attempt (logged once as a warning) and the normal reconnection takes over. A single message that cannot be handled is still skipped.
- Every websocket message was handled twice: Leakomatic's server sends each message twice, a few milliseconds apart. An identical copy received within 5 seconds is now dropped, so each event updates the entities once.
- Total Volume showed a thousandth of the real value (the device's volume is already in m³ and was divided by 1000), and updates from flow events and water meter calibration never arrived (their volume, in litres, has a different field name). Both are fixed, and the sensor now also follows device updates. Its device class is now *water*, so it can be used in the Energy dashboard. If you had the sensor enabled with a water meter, its value jumps to the correct (1000 times larger) reading after the update, which the long-term statistics count as consumption once; correct that entry under Developer tools → Statistics.
- Temperature and Pressure become unknown when the analog sensor is reported as not connected, instead of keeping the last reading.
- Flow Test, Quick Test and Tightness Test: their attributes (the test's settings) disappeared after the first alarm message and only came back after a restart, and a setting changed in Leakomatic's app never showed. The settings are now kept separately and follow configuration changes. The alarm state now comes from the device's list of active alarms at startup and on every device update, so two tests alarming at the same time both show (previously only one), and resetting the alarms clears the sensors.
- The attributes of Flow Test, Quick Test and Tightness Test (for example alarm delay and index limit) were shown with their raw keys, because their translations were in the wrong place. They are now shown with translated names in English and Swedish. The unused `translations/strings.json` is removed.
- Mode select and Reset Alarms button: a failed mode change or alarm reset was only logged, and the caller (the UI, an automation or a script) was told it succeeded. It now fails with an error (translated to English and Swedish), so an automation that sets the mode stops at that step and its trace shows the error.
- Online Status: when Leakomatic reported the device offline (`device_offline`), the sensor was set to online. It is now set to offline, and back to online with the next message from the device.
- If Leakomatic could not be reached when Home Assistant started (network, DNS or server problems), the integration failed and stayed failed until it was reloaded by hand. Home Assistant now retries the setup automatically until Leakomatic can be reached.
- If the websocket token could not be fetched at startup, real-time updates never started and all entities stayed at their startup values until Home Assistant was restarted. The reconnection loop now logs in and fetches the token itself, and keeps retrying with the normal backoff.
- The login session with Leakomatic was never renewed. Once it expired, fetching device data and the websocket token failed, and changing the mode or resetting alarms was logged as successful without anything happening, until Home Assistant was restarted. An expired session is now detected (redirect to the login page, HTTP 401, or a web page where data was expected); the integration logs in again once and retries. If Leakomatic then rejects the password, Home Assistant asks you to re-authenticate.
- Network and server errors during login were reported as "Invalid email or password". They are now reported as "Could not connect to Leakomatic", and only a login that Leakomatic actually rejects counts as wrong credentials.
- Websocket message types without a handler (for example `configuration_added`) no longer log `Error in WebSocket callback: name 'self' is not defined`. They are now logged at debug level.
- An error while handling a websocket message in one entity platform no longer stops the same message from reaching the other platforms.
- Mode select: only updated by messages for its own device. Previously a mode change on one device could change the select of another device on the same account.
- Total volume sensor: water meter calibration messages now update the sensor (they were read from the wrong place in the message), and an invalid value is logged instead of raising a second error.
- Entities that are disabled in the entity registry are no longer updated by websocket messages, which could raise an error.
- Unloading or reloading the integration now stops the websocket connection immediately. Previously the old connection loop was only told to stop and could keep running: up to 30 seconds while connected, or until its next retry (up to 12 hours) while waiting to reconnect.
- WebSocket Connectivity sensor: it showed "connected" from startup, before any connection existed, and as soon as the subscription was sent, even if the server then refused it. It now starts as disconnected and turns on only when the server confirms the subscription. A refused subscription or a server disconnect that refuses the token is handled as a failed attempt (with the normal backoff and a new token) instead of being logged as `Unknown message type in response`.
- Login: if the user ID cannot be found on the page after login, the integration no longer fails with a misleading "invalid credentials" error. It logs a clear warning that real-time updates will not be available.

### Changed
- README rewritten: what you need, installation and configuration, the entities in tables, automation examples (away and home with the house, pause during irrigation, leak alarm notification, reminder before the pause ends, water flow per hour and day), how data is updated, known limitations, troubleshooting and removal.
- WebSocket Connectivity uses its translated name (in Swedish "WebSocket-anslutning"); a hard-coded English name overrode the translation. The entity ID is unchanged.
- Internal: the simple sensors (quick test index, flow duration, signal strength, longest tightness period, temperature, pressure) are entity descriptions with one sensor class instead of six near-identical classes, and the mode select uses the one mapping between mode numbers and options. What the entities show is unchanged, which a snapshot test of all entities recorded before the change checks.
- Internal: the client keeps one HTTP session (created with Home Assistant's helper, with its own cookie jar) instead of opening a new session for every request, and closes it when the integration unloads or its setup fails. The websocket uses Home Assistant's cached SSL context.
- Config flow: the entry is identified by the Leakomatic account (its user ID), so the same account cannot be added twice even if the email is written differently, and it is named after the account's email instead of the first device. Existing entries are updated at the next start; a name you have changed yourself is kept. The unused `device_id` is removed from the entry, and the password field is masked.
- README: corrected claims that did not match the code (the stuck-connection check is 120 seconds of silence, not 10 minutes; there is no polling fallback), added installation with HACS and removal instructions, a no-restart way to toggle debug logging, and what the integration cannot do (control the valve directly, change the device configuration). Removed two stray files from the repository root.
- English entity names: "Flow Duration" is now "Last Flow Duration" and "Tightness Period" is now "Longest Tightness Period", matching the Swedish names and the README. Existing entity IDs are kept; only new installations get IDs from the new names. Swedish: "Larmfördröjning" is used for all three alarm test sensors (two of them said "Alarmfördröjning").
- Manifest: `iot_class` is now `cloud_push` (the previous value `push` is not valid and failed Home Assistant's manifest validation), `integration_type` is set to `hub`, `aiohttp` is no longer listed as a requirement (it is part of Home Assistant), and the minimum `websockets` version is 15.0.1 (the version whose API the integration uses, and Home Assistant's own minimum).
- `hacs.json`: removed `filename`. It pointed to a zip file that the releases never contained.
- Swedish: the state *clear* of Flow Test, Quick Test and Tightness Test is now shown as "OK" for all three (it was "Klar" for two and "Klart" for one).
- Flow Test, Quick Test and Tightness Test are now enum sensors (device class `enum`, options `clear`, `warning`, `alarm`). The state values are unchanged, so automations keep working. An unknown alarm level now makes the sensor unknown; previously it was logged and the old state was kept.
- Binary sensors show *unknown* instead of *off* when the data needed is missing or invalid. Flow Indicator is unknown after startup until the first flow event (it was forced to off). Online Status is unknown after startup until the first message from the device (it could show offline while the device was up). Valve is unknown if the valve state is missing or invalid (it showed closed).
- Minimum Home Assistant version is now documented as 2024.8.0 (in the README and `hacs.json`). The integration already required it (device registry `model_id`); the previously stated 2023.x versions were wrong.
- Internal: runtime data is stored in the config entry (`entry.runtime_data`) instead of `hass.data`, and each platform's websocket listener is removed when the integration is unloaded or reloaded.
- Logging: the server's scheduled websocket disconnect (typically nightly) and the reconnection that follows are logged at debug/info level instead of warning. A warning is now logged when the quick reconnection attempts fail and the longer retry intervals start (phase 2 and phase 3), which is when something is actually wrong. A failed token refresh during reconnection no longer logs both an error and a warning.

### Added
- Diagnostics: download them from the integration or a device page. They contain the device data and the connection state, with personal data redacted and the alarm and event history left out.
- Pause Ends sensor: when the pause mode ends and the device returns to its previous mode (a timestamp, unknown when the device is not paused).
- Online Status turns off when nothing has been heard from the device for 15 minutes while the connection to Leakomatic was up. The device reports every 5 minutes, so this is two missed reports. Previously the sensor stayed on for as long as Leakomatic did not send an explicit offline message. Logged once at info level.
- Entities become unavailable when the connection to Leakomatic has been down for 5 minutes, instead of showing their last values as if they were current (possibly for hours while the integration waits to reconnect). The WebSocket Connectivity sensor stays available and shows the connection state. Short disconnects, such as the server's nightly one, do not affect availability. Both changes are logged once at info level.
- Reauthentication: if Leakomatic rejects the stored password (for example after you change it), Home Assistant asks for the new password instead of just failing.
- Test suite based on `pytest-homeassistant-custom-component`, run on every pull request by a GitHub Actions workflow.
- Validation on every pull request: hassfest (manifest, translations, services), the HACS action and Ruff (lint). Unused imports found by Ruff are removed.

## [0.1.6] - 2026-07-01

### Fixed
- A valid CLEAR alarm level (`0`) is no longer logged as `Unknown alarm level received: 0` (type mismatch between the websocket payload and the alarm level values). Thanks to @skallan.
- Websocket reconnection: successful (re)connections are recognised, so the phased backoff no longer escalates to hour-long or indefinite waits after a normal reconnect. Adds detection of stale sockets (120 seconds without any message triggers a reconnect) and removes unused health-check code. Thanks to @skallan.

## [0.1.5] - 2026-04-19

### Fixed
- Restored `services.yaml` with a valid definition for the `change_mode` service so Home Assistant Core 2026.4+ no longer logs `NoneType: None` when loading an empty or missing integration service schema.

## [0.1.4] - 2026-04-06

### Fixed
- Replaced the deprecated `async_add_job` with `add_job` for connectivity callbacks, ahead of its removal in Home Assistant 2025.4.

## [0.1.3] - 2025-08-05

### Changed
- Updated temperature sensor icon to use 'mdi:thermometer-water' for better visual representation
- Removed redundant debug logging for mode change results in LeakomaticClient
- Updated README documentation to reflect recent changes

## [0.1.2] - 2025-05-16

### Added
- Temperature sensor support with real-time updates
- Pressure sensor support with real-time updates
- Enhanced analog sensor message handling
- Improved last seen timestamp handling for online status
- More detailed logging for sensor updates

### Changed
- Refined message handling system for better reliability
- Enhanced error handling for timestamp parsing
- Improved sensor value type conversion and validation

### Removed
- `change_mode` service as this functionality is now handled through the mode select entity

### Fixed
- Timestamp parsing issues in online status sensor
- Sensor value conversion for tightness period
- Analog sensor message handling for temperature and pressure

## [0.1.1] - 2025-05-15

### Added
- Support for multiple devices per account
- Enhanced WebSocket message handling system
- Last seen timestamp for online status monitoring
- Improved error handling and logging
- More detailed documentation

### Changed
- Improved WebSocket connection management
- Enhanced multi-device support in services
- Updated README with comprehensive feature documentation
- Refined error messages and logging

### Fixed
- WebSocket reconnection handling
- Device state updates reliability
- Service call handling for multiple devices

## [0.1.0] - 2025-05-14

### Added
- Initial release of the Leakomatic Integration
- Real-time WebSocket connection for device monitoring
- Support for device mode control (Home/Away/Pause)
- Multiple sensor types:
  - Quick Test Index
  - Flow Duration
  - Signal Strength
  - Longest Tightness Period
- Binary sensors:
  - Flow Indicator
  - Online Status
  - Valve State
- Select entity for device mode control
- Reset Alarms button
- Alarm test sensors for Flow, Quick, and Tightness tests
- Full localization support (English and Swedish)
- Automatic reconnection handling
- Service for changing device operating mode
- Comprehensive documentation 