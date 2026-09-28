# Changelog

All notable changes to the Leakomatic Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
- Binary sensors show *unknown* instead of *off* when the data needed is missing or invalid. Flow Indicator is unknown after startup until the first flow event (it was forced to off). Online Status is unknown after startup until the first message from the device (it could show offline while the device was up). Valve is unknown if the valve state is missing or invalid (it showed closed).
- Minimum Home Assistant version is now documented as 2024.8.0 (in the README and `hacs.json`). The integration already required it (device registry `model_id`); the previously stated 2023.x versions were wrong.
- Internal: runtime data is stored in the config entry (`entry.runtime_data`) instead of `hass.data`, and each platform's websocket listener is removed when the integration is unloaded or reloaded.
- Logging: the server's scheduled websocket disconnect (typically nightly) and the reconnection that follows are logged at debug/info level instead of warning. A warning is now logged when the quick reconnection attempts fail and the longer retry intervals start (phase 2 and phase 3), which is when something is actually wrong. A failed token refresh during reconnection no longer logs both an error and a warning.

### Added
- Entities become unavailable when the connection to Leakomatic has been down for 5 minutes, instead of showing their last values as if they were current (possibly for hours while the integration waits to reconnect). The WebSocket Connectivity sensor stays available and shows the connection state. Short disconnects, such as the server's nightly one, do not affect availability. Both changes are logged once at info level.
- Reauthentication: if Leakomatic rejects the stored password (for example after you change it), Home Assistant asks for the new password instead of just failing.
- Test suite based on `pytest-homeassistant-custom-component`, run on every pull request by a GitHub Actions workflow.

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