# Changelog

All notable changes to the Leakomatic Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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