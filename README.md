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
- Detection of stale connections: a websocket that has been silent for 120 seconds is reconnected
- Entities become unavailable when the connection to Leakomatic has been down for 5 minutes
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
- Localization (English and Swedish) of entity names, states, attributes and error messages
- Button to reset warnings or alarms
- All devices on the account are set up (tested with one device)

## Requirements

- Home Assistant 2024.8.0 or newer (tested with 2026.9)
- Python packages (installed by Home Assistant from the manifest):
  - beautifulsoup4 >= 4.9.3
  - websockets >= 15.0.1

## Available Entities

The integration provides the following entities:

### Sensors

- **Quick Test Index**: Displays the current quick test measurement value
  - Numerical value indicating water flow characteristics
  - Updates in real-time when quick tests are performed

- **Last Flow Duration**: Shows the duration of the last completed water flow
  - Measured in seconds
  - Updates when a flow event completes
  - Helps track water usage patterns

- **Longest Tightness Period**: Shows the longest period of no water flow
  - Measured in seconds
  - Updates in real-time through WebSocket events
  - Helps monitor system tightness and potential leaks

- **Temperature** and **Pressure**: Readings from a sensor connected to the device's analog input ("Analog In" in Leakomatic's settings)
  - Measured in °C and bar, updated in real time
  - Unknown when the sensor is not connected
  - Disabled by default; only useful if such a sensor is installed

- **Total Volume**: The reading of a water meter connected to the device's pulse input ("AUX In" with a pulse volume in Leakomatic's settings)
  - Measured in cubic meters (m³), device class water, so it can be used as a water source in Home Assistant's Energy dashboard
  - Updated on flow events, water meter calibration and device updates
  - Disabled by default; devices without a water meter report 0

Temperature, Pressure and Total Volume follow the data Leakomatic sends, but have not been tested with real sensors or a real water meter connected. Reports are welcome.

- **Pause Ends**: Shows when the pause mode ends and the device returns to its previous mode
  - A timestamp; Unknown when the device is not paused
  - The pause length is set in Leakomatic's app ("Time in pause mode")
  - Useful in dashboards and automations, for example to notify before monitoring resumes

- **Signal Strength**: Shows the WiFi signal strength (RSSI) of the device
  - Measured in dBm
  - Updates in real-time through WebSocket events
  - Helps monitor device connectivity quality
### Binary Sensors

- **Flow Indicator**: Shows if water is currently flowing
  - States: On (water flowing), Off (no water flow), Unknown (after startup, until the first flow event; the startup data from Leakomatic does not tell whether water is flowing)
  - Updates in real-time through WebSocket flow events
  - Useful for tracking active water usage and flow patterns

- **Online Status**: Shows if the device is currently online
  - States: On (online), Off (offline), Unknown (after startup, until the first message from the device)
  - Turns off when Leakomatic reports the device offline, or when nothing has been heard from the device for 15 minutes while the connection to Leakomatic was up (the device reports every 5 minutes). Turns on again with the next message from the device
  - Updates in real-time through WebSocket events
  - Includes a last_seen attribute showing the timestamp of the last received message
  - Useful for monitoring device connectivity and troubleshooting connection issues

- **Valve**: Shows the current state of the water valve
  - States: On (valve open), Off (valve closed), Unknown (valve state missing or invalid)
  - Updates in real-time through WebSocket events
  - Helps monitor valve operation and status

- **WebSocket Connectivity**: Shows the status of the WebSocket connection to the Leakomatic API
  - States: On (connected), Off (disconnected)
  - Turns on only when the Leakomatic server has confirmed the subscription, so On means real-time updates are actually flowing
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
  - If Leakomatic does not accept the change, the action fails with an error, so the UI shows it and an automation or script stops at that step

### Buttons

- **Reset Alarms**: Allows resetting all active warnings or alarms on the device
  - Located in the device configuration section
  - Useful for clearing alarm states after resolving issues
  - If the reset fails, the press fails with an error

### Alarm Test Sensors

The three alarm test sensors are enum sensors (device class `enum`) with the options `clear`, `warning` and `alarm`. Use these values in automations; the UI shows them translated. If Leakomatic reports an alarm level the integration does not know, the sensor shows Unknown instead of keeping its previous state.

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

- Device updates (mode changes)
- Status messages (valve state, signal strength)
- Alarm triggers (flow, quick test, tightness test)
- Flow indicator updates
- Quick test index calculations
- Tightness test period monitoring
- Temperature sensor readings
- Pressure sensor readings
- Online status updates with timestamps

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
- **Stale Connection Detection**: If an open websocket receives nothing for 120 seconds (not even the server's pings, which come every few seconds), it is treated as dead and reconnected
- **Availability**: If the WebSocket connection has been down for 5 minutes, all entities except WebSocket Connectivity become unavailable, so stale values are not shown as current. They become available again as soon as the connection is back. Short disconnects, such as the server's nightly one, are not visible.
- **Resource Efficient**: Long retry intervals prevent excessive CPU/network usage

This strategy eliminates the need for manual integration reloads while maintaining robust connectivity to the Leakomatic API.

## Supported Languages

This integration supports the following languages:
- English (en)
- Swedish (sv)

The integration will automatically use the language that matches your Home Assistant language settings. All sensor names, states, the names of the alarm test sensors' attributes (for example the flow test's alarm delay), error messages and UI elements will be displayed in your chosen language.

## Installation

### With HACS

1. In HACS, open the menu (⋮) → Custom repositories, and add `https://github.com/johanwilliams/leakomatic_api` with the type Integration
2. Search for "Leakomatic" in HACS and download it
3. Restart Home Assistant
4. Follow the configuration steps below

### Manually

1. Copy the `custom_components/leakomatic` directory from the latest [release](https://github.com/johanwilliams/leakomatic_api/releases) to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Follow the configuration steps below

## Removal

1. Go to Settings → Devices & services → Leakomatic, open the menu (⋮) on the entry and choose Delete
2. If you installed with HACS, remove the integration in HACS; if you installed manually, delete `custom_components/leakomatic`
3. Restart Home Assistant

Removing the integration does not change anything on the Leakomatic device or in your Leakomatic account.

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

After adding this configuration, restart Home Assistant to apply the changes. Debug logs will appear in your Home Assistant logs and can be viewed under Settings → System → Logs.

To turn debug logging on or off without a restart, call the `logger.set_level` action with `custom_components.leakomatic: debug` (or `warning` to turn it off again).

## Troubleshooting

If you encounter any issues with the integration:

1. Enable debug logging as described above
2. Check the logs for detailed information
3. Monitor the WebSocket Connectivity binary sensor for connection status
4. Common issues and solutions:
   - Authentication failures: If Leakomatic rejects the stored password (for example after you changed it), Home Assistant shows a notification asking you to re-authenticate. Enter the current password there; the integration reloads by itself.
   - Connection issues: If Leakomatic cannot be reached when Home Assistant starts, the integration shows "Retrying setup" under Settings → Devices & services and keeps trying by itself. Check your network connection and firewall settings if it does not recover.
   - Missing updates: Check WebSocket connection status in the logs and the WebSocket Connectivity sensor
   - Sensor state issues: Verify device connectivity and data flow
   - Service call failures: Check entity IDs and mode parameters
   - Multiple device support: Ensure proper device selection when using services
   - Persistent disconnections: The integration will automatically retry with a multi-phase strategy
   - Stuck connections: a websocket that is silent for 120 seconds is reconnected automatically
5. Reading the log:
   - The Leakomatic server closes the websocket on a schedule (typically once per night). The integration reconnects within seconds; this is logged at debug/info level and needs no action.
   - `Online Status - Nothing heard from the device for 15 minutes, marking it offline` (info) means the device has stopped reporting while the connection to Leakomatic works. Check the device's power and network.
   - `No connection to Leakomatic for 5 minutes, marking entities unavailable` (info) and `Connection to Leakomatic restored, entities are available again` (info) mark when the entities became unavailable and available again.
   - A warning such as `WebSocket reconnection failed 10 times, retrying every 6 hours (phase 2)` means the integration could not reconnect and has switched to longer retry intervals. Check your network connection and the Leakomatic service.

## Development Status

This integration is in active development and is not affiliated with Leakomatic. It uses the same cloud service as Leakomatic's web page and app; there is no official API, so a change on Leakomatic's side can break it. See the [changelog](CHANGELOG.md) for the current version and what has changed.

The integration reads the device and can change the mode and reset alarms. It cannot open or close the valve directly (Leakomatic's cloud offers no such command) and does not change the device's configuration; use Leakomatic's app for that.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Running the tests

The tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) and run automatically on every pull request. To run them locally you need Python 3.14 on Linux or macOS (Home Assistant does not run on Windows; use WSL or a container there):

```bash
pip install -r requirements_test.txt
python -m pytest
```

Test data must be invented: do not add payloads from a real account, since they contain serial numbers, user IDs and locations.

Every pull request is also checked by [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) (manifest, translations, services), the [HACS action](https://hacs.xyz/docs/publish/action) and [Ruff](https://docs.astral.sh/ruff/). Run the linter locally with:

```bash
pip install ruff
ruff check .
```

## License

This project is licensed under the terms of the license included in the repository. 