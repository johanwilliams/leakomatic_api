# Changelog

All notable changes to the Leakomatic Integration for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-03-19

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