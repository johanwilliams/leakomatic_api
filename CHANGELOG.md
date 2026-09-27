# Changelog

All notable changes to the Leakomatic Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Websocket message types without a handler (for example `configuration_added`) no longer log `Error in WebSocket callback: name 'self' is not defined`. They are now logged at debug level.
- An error while handling a websocket message in one entity platform no longer stops the same message from reaching the other platforms.
- Mode select: only updated by messages for its own device. Previously a mode change on one device could change the select of another device on the same account.
- Total volume sensor: water meter calibration messages now update the sensor (they were read from the wrong place in the message), and an invalid value is logged instead of raising a second error.
- Entities that are disabled in the entity registry are no longer updated by websocket messages, which could raise an error.
- Login: if the user ID cannot be found on the page after login, the integration no longer fails with a misleading "invalid credentials" error. It logs a clear warning that real-time updates will not be available.

### Changed
- Logging: the server's scheduled websocket disconnect (typically nightly) and the reconnection that follows are logged at debug/info level instead of warning. A warning is now logged when the quick reconnection attempts fail and the longer retry intervals start (phase 2 and phase 3), which is when something is actually wrong. A failed token refresh during reconnection no longer logs both an error and a warning.

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