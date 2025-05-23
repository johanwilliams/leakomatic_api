# Leakomatic Integration for Home Assistant

This integration allows you to connect your Leakomatic water leak sensors to Home Assistant. Leakomatic is a water protection system that has been available since 2002, providing leak monitoring and automatic water shutoff capabilities for various types of properties. For more information about Leakomatic, visit [leakomatic.com](https://www.leakomatic.com).

## About Leakomatic

Water damage is a common issue in properties that can lead to significant costs and inconvenience. Leakomatic provides a monitoring system that can help prevent such damage by detecting leaks and automatically controlling water flow.

### System Capabilities

- **Leak Detection**: Monitors water flow and detects potential leaks
- **Automatic Control**: Can automatically shut off water supply when issues are detected
- **Property Types**: Compatible with various property types including:
  - Residential properties
  - Commercial buildings
  - Construction sites
  - Industrial facilities

## Features

- Real-time updates via WebSocket connection with automatic reconnection handling
- Comprehensive device monitoring:
  - Device mode monitoring and control (Home/Away/Pause)
  - Quick test index monitoring
  - Flow duration monitoring
  - Longest tightness period monitoring
  - Total volume monitoring
  - Flow indicator monitoring
  - Online status monitoring with last seen timestamp
  - Signal strength monitoring
  - Valve state monitoring
  - Alarm state monitoring (Flow/Quick/Tightness tests)
  - Device information display (model, software version, location)
- Advanced message handling system for reliable updates
- Full localization support for all sensor names and states
- Button to reset alarms
- Support for multiple devices per account

## Requirements

- Home Assistant 2023.1.0 or newer
- Python packages:
  - aiohttp >= 3.8.0
  - beautifulsoup4 >= 4.9.3
  - websockets >= 13.1

## Available Entities

The integration provides the following entities:

### Sensors

- **Quick Test Index**: Displays the current quick test measurement value
  - Numerical value indicating water flow characteristics
  - Updates in real-time when quick tests are performed

- **Flow Duration**: Shows the duration of the last completed water flow
  - Measured in seconds
  - Updates when a flow event completes
  - Helps track water usage patterns

- **Signal Strength**: Shows the WiFi signal strength (RSSI) of the device
  - Measured in dBm
  - Updates in real-time through WebSocket events
  - Helps monitor device connectivity quality

- **Temperature**: Shows the current temperature reading from the device
  - Measured in Celsius (°C)
  - Updates in real-time through analog sensor messages
  - Rounds values to 1 decimal place
  - Helps monitor ambient temperature conditions

- **Pressure**: Shows the current water pressure reading from the device
  - Measured in bar
  - Updates in real-time through analog sensor messages
  - Rounds values to 1 decimal place
  - Helps monitor water pressure conditions

- **Longest Tightness Period**: Shows the longest period of no water flow
  - Measured in seconds
  - Updates in real-time through WebSocket events
  - Helps monitor system tightness and potential leaks

- **Total Volume**: Shows the total water volume (water meter value)
  - Measured in cubic meters (m³)
  - Updates in real-time through WebSocket events
  - Disabled by default (can be enabled in entity settings)
  - Helps track total water consumption
  - Updates on flow events and water meter calibration

### Binary Sensors

- **Flow Indicator**: Shows if water is currently flowing
  - States: On (water flowing), Off (no water flow)
  - Updates in real-time through WebSocket flow events
  - Useful for tracking active water usage and flow patterns

- **Online Status**: Shows if the device is currently online
  - States: On (online), Off (offline), Unknown (initial state)
  - Updates in real-time through WebSocket events
  - Automatically sets to "On" when receiving any activity message from the device
  - Automatically sets to "Off" when receiving a device update with is_online=False
  - Includes a last_seen attribute showing the timestamp of the last received message
  - Useful for monitoring device connectivity and troubleshooting connection issues

- **Valve**: Shows the current state of the water valve
  - States: On (valve open), Off (valve closed)
  - Updates in real-time through WebSocket events
  - Helps monitor valve operation and status

### Select Entities

- **Mode**: Allows changing the operating mode of your Leakomatic device
  - Options: Home, Away, Pause
  - Updates in real-time through WebSocket events
  - Can be used to change the device mode directly from Home Assistant

### Buttons

- **Reset Alarms**: Allows resetting all active alarms on the device
  - Located in the device configuration section
  - Useful for clearing alarm states after resolving issues

### Alarm Test Sensors

- **Flow Test**: Monitors flow alarms and provides alarm state information
  - States: Clear (0), Warning (1), Alarm (2)
  - Updates in real-time through WebSocket alarm events
  - Provides early warning of potential water flow issues

- **Quick Test**: Monitors quick test alarms
  - States: Clear (0), Warning (1), Alarm (2)
  - Updates in real-time through WebSocket alarm events
  - Helps detect and prevent water leaks

- **Tightness Test**: Monitors tightness test alarms
  - States: Clear (0), Warning (1), Alarm (2)
  - Updates in real-time through WebSocket alarm events
  - Helps detect and prevent water leaks

## Message Handling System

The integration implements a robust message handling system that processes various types of WebSocket messages:

- Device updates
- Alarm triggers
- Flow updates
- Quick test updates
- Tightness test updates
- Status messages
- Device offline notifications
- Ping messages for connection monitoring

Each message type is handled by specific handlers that update the relevant entities in real-time, ensuring accurate and timely state updates.

## Supported Languages

This integration supports the following languages:
- English (en)
- Swedish (sv)

The integration will automatically use the language that matches your Home Assistant language settings. All sensor names, states, and UI elements will be displayed in your chosen language.

## Installation

1. Copy the `custom_components/leakomatic` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Follow the configuration steps below

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Leakomatic"
4. Enter your email and password
5. Click "Submit"

The integration will automatically:
- Connect to your Leakomatic device
- Set up real-time monitoring via WebSocket
- Create all necessary entities

## Debug Logging

To enable debug logging for this integration, add the following to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.leakomatic: debug
```

After adding this configuration, restart Home Assistant to apply the changes. Debug logs will appear in your Home Assistant logs and can be viewed in the Developer Tools > Logs section of the Home Assistant UI.

## Troubleshooting

If you encounter any issues with the integration:

1. Enable debug logging as described above
2. Check the logs for detailed information
3. Common issues and solutions:
   - Authentication failures: Verify your email and password
   - Connection issues: Check your network connection and firewall settings
   - Missing updates: Check WebSocket connection status in the logs
   - Sensor state issues: Verify device connectivity and data flow
   - Service call failures: Check entity IDs and mode parameters
   - Multiple device support: Ensure proper device selection when using services

## Development Status

This integration is currently in active development. Current version: 0.1.0

Future enhancements planned:
- Enhanced error handling and recovery
- More detailed alarm state reporting
- Historical data analysis features
- Additional sensor types for various device metrics
- Improved WebSocket connection management
- Enhanced multi-device support

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the terms of the license included in the repository. 