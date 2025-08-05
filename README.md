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

- Real-time updates via WebSocket connection with persistent reconnection handling
- Multi-phase retry strategy for robust connectivity:
  - Phase 1: Quick retries (10 attempts with exponential backoff)
  - Phase 2: Medium-term retries (every 6 hours for 24 hours)
  - Phase 3: Long-term retries (every 12 hours indefinitely)
- Automatic WebSocket token refresh every 24 hours
- Health monitoring to detect and recover from stuck connections
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
  - WebSocket connectivity status monitoring
- Advanced message handling system for reliable updates
- Full localization support for all sensor names and states
- Button to reset warnings or alarms
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

- **Longest Tightness Period**: Shows the longest period of no water flow
  - Measured in seconds
  - Updates in real-time through WebSocket events
  - Helps monitor system tightness and potential leaks

- **Temperature**: Shows the current temperature reading from the device if available
  - Measured in Celsius (°C)
  - Updates in real-time through analog sensor messages
  - Helps monitor ambient temperature conditions

- **Pressure**: Shows the current water pressure reading from the device if available
  - Measured in bar
  - Updates in real-time through analog sensor messages
  - Helps monitor water pressure conditions

- **Total Volume**: Shows the total water volume (water meter value) if available
  - Measured in cubic meters (m³)
  - Updates in real-time through WebSocket events
  - Disabled by default (can be enabled in entity settings)
  - Helps track total water consumption
  - Updates on flow events and water meter calibration

- **Signal Strength**: Shows the WiFi signal strength (RSSI) of the device
  - Measured in dBm
  - Updates in real-time through WebSocket events
  - Helps monitor device connectivity quality
### Binary Sensors

- **Flow Indicator**: Shows if water is currently flowing
  - States: On (water flowing), Off (no water flow)
  - Updates in real-time through WebSocket flow events
  - Useful for tracking active water usage and flow patterns

- **Online Status**: Shows if the device is currently online
  - States: On (online), Off (offline), Unknown (initial state)
  - Updates in real-time through WebSocket events
  - Includes a last_seen attribute showing the timestamp of the last received message
  - Useful for monitoring device connectivity and troubleshooting connection issues

- **Valve**: Shows the current state of the water valve
  - States: On (valve open), Off (valve closed)
  - Updates in real-time through WebSocket events
  - Helps monitor valve operation and status

- **WebSocket Connectivity**: Shows the status of the WebSocket connection to the Leakomatic API
  - States: On (connected), Off (disconnected)
  - Category: Diagnostic
  - Updates in real-time when connection status changes
  - Includes reconnection phase information in state attributes
  - Useful for monitoring integration connectivity and troubleshooting connection issues
  - Shows current retry phase during reconnection attempts

### Select Entities

- **Mode**: Allows changing the operating mode of your Leakomatic device
  - Options: Home, Away, Pause
  - Updates in real-time through WebSocket events
  - Can be used to change the device mode directly from Home Assistant

### Buttons

- **Reset Alarms**: Allows resetting all active warnings or alarms on the device
  - Located in the device configuration section
  - Useful for clearing alarm states after resolving issues

### Alarm Test Sensors

- **Flow Test**: Monitors flow alarms and provides alarm state information
  - States: Clear, Warning, Alarm
  - Updates in real-time through WebSocket alarm events
  - Detects if water flows longer than predefined time limits based on home or away mode, helping prevent major water damage

- **Quick Test**: Monitors quick test alarms
  - States: Clear, Warning, Alarm
  - Updates in real-time through WebSocket alarm events
  - Calculates a real-time index from pulse activity over the past hour to detect sudden drip leaks or changes in water usage trends

- **Tightness Test**: Monitors tightness test alarms
  - States: Clear, Warning, Alarm
  - Updates in real-time through WebSocket alarm events
  - Analyzes pulse activity over a 24-hour period to identify hidden leaks by ensuring at least one period with no water flow occurs

## Message Handling System

The integration implements a robust message handling system that processes various types of WebSocket messages:

- Device updates (mode changes, valve state)
- Alarm triggers (flow, quick test, tightness test)
- Flow indicator updates
- Quick test index calculations
- Tightness test period monitoring
- Temperature sensor readings
- Pressure sensor readings
- Online status updates with timestamps
- Connection health monitoring

Each message type is handled by specific handlers that update the relevant entities in real-time, ensuring accurate and timely state updates.

## Persistent Reconnection Strategy

The integration implements a robust multi-phase reconnection strategy to ensure reliable connectivity:

### Phase 1: Quick Retries
- 10 attempts with exponential backoff (5 seconds to 1 hour)
- Includes jitter (±20%) to prevent thundering herd
- Used for temporary network issues or brief service interruptions

### Phase 2: Medium-term Retries
- 4 attempts every 6 hours (24 hours total)
- Used for longer network outages or service issues
- Provides balance between responsiveness and resource usage

### Phase 3: Long-term Retries
- Indefinite retries every 12 hours
- Ensures the integration never gives up permanently
- Maintains connectivity even during extended outages

### Additional Features
- **Token Refresh**: Automatically refreshes WebSocket tokens every 24 hours
- **Health Monitoring**: Detects stuck connections (no messages for 10+ minutes) and forces reconnection
- **Graceful Degradation**: Integration continues working with polling even when WebSocket is down
- **Resource Efficient**: Long retry intervals prevent excessive CPU/network usage

This strategy eliminates the need for manual integration reloads while maintaining robust connectivity to the Leakomatic API.

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
3. Monitor the WebSocket Connectivity binary sensor for connection status
4. Common issues and solutions:
   - Authentication failures: Verify your email and password
   - Connection issues: Check your network connection and firewall settings
   - Missing updates: Check WebSocket connection status in the logs and the WebSocket Connectivity sensor
   - Sensor state issues: Verify device connectivity and data flow
   - Service call failures: Check entity IDs and mode parameters
   - Multiple device support: Ensure proper device selection when using services
   - Persistent disconnections: The integration will automatically retry with a multi-phase strategy
   - Stuck connections: Health monitoring will detect and recover from stuck connections automatically

## Development Status

This integration is currently in active development. Current version: 0.1.3

Recent improvements:
- Implemented persistent WebSocket reconnection with multi-phase retry strategy
- Added WebSocket connectivity binary sensor for real-time connection monitoring
- Enhanced error handling and recovery mechanisms
- Improved token management with automatic refresh

Future enhancements planned:
- Historical data analysis features
- Additional alarm state details and configuration options
- More detailed device diagnostics and health monitoring
- Enhanced error reporting and user notifications
- Advanced connectivity analytics and reporting

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the terms of the license included in the repository. 