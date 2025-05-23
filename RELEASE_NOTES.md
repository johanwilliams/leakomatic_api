# Release Notes - Version 0.1.2

## 🎉 New Features

### New Sensors
- Added support for temperature monitoring with real-time updates
- Added support for pressure monitoring with real-time updates

### Enhanced Monitoring
- Improved online status tracking with better timestamp handling
- More detailed logging for better troubleshooting

## 🔄 Changes

### Improved Reliability
- Enhanced message handling system for more stable operation
- Better error handling for various edge cases
- Improved sensor value validation and conversion

### Service Changes
- Removed the `change_mode` service as this functionality is now handled through the mode select entity
  - Users should update their automations to use the mode select entity instead
  - This change provides a more consistent and user-friendly way to change device modes

## 🐛 Bug Fixes

- Fixed issues with timestamp parsing in the online status sensor
- Resolved sensor value conversion problems for the tightness period
- Improved handling of analog sensor messages for temperature and pressure readings

## 📝 Documentation

The integration's documentation has been updated to reflect these changes. Please refer to the README for detailed information about the new features and updated functionality.

## 🔧 Migration Notes

If you're upgrading from a previous version:
1. Update your automations that use the `change_mode` service to use the mode select entity instead
2. The new temperature and pressure sensors will be automatically added to your devices
3. No configuration changes are required for the upgrade

## 🚀 Installation

To install this version:
1. Update the integration through HACS or manually update the files
2. Restart Home Assistant
3. The new features will be automatically available 