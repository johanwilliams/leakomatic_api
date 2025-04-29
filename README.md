# Leakomatic Integration for Home Assistant

This integration allows you to connect your Leakomatic water leak sensors to Home Assistant.

## Features

- Real-time updates via WebSocket connection
- Device mode monitoring (Home/Away/Pause)
- Quick test index monitoring
- Flow duration monitoring
- Flow indicator monitoring
- Online status monitoring
- Device information display (model, software version, location)
- Automatic reconnection handling
- Full localization support for all sensor names and states
- Service to change device operating mode

## Available Sensors

The integration provides the following sensors:

- **Mode Sensor**: Shows the current operating mode of your Leakomatic device
  - States: Home (0), Away (1), Pause (2)
  - Includes device status attributes like alarm state and last seen time

- **Quick Test Index**: Displays the current quick test measurement value
  - Numerical value indicating water flow characteristics
  - Updates in real-time when quick tests are performed

- **Flow Duration**: Shows the duration of the last completed water flow
  - Measured in seconds
  - Updates when a flow event completes
  - Helps track water usage patterns

- **Flow Indicator**: Binary sensor showing if water is currently flowing
  - States: On (water flowing), Off (no water flow), Unknown (initial state)
  - Updates in real-time through WebSocket events
  - Note: Due to an API limitation, the initial state is set to Unknown until the first flow update is received

- **Online Status**: Binary sensor showing if the device is currently online
  - States: On (online), Off (offline), Unknown (initial state)
  - Updates in real-time through WebSocket events
  - Automatically sets to "On" when receiving any activity message from the device
  - Automatically sets to "Off" when receiving a device update with is_online=False

## Services

The integration provides the following service:

- **leakomatic.change_mode**: Change the operating mode of your Leakomatic device
  - Parameters:
    - `entity_id`: The entity ID of the Leakomatic device
    - `mode`: The new mode to set (home, away, or pause)
  - Example usage in automations or scripts:
    ```yaml
    service: leakomatic.change_mode
    target:
      entity_id: sensor.leakomatic_mode
    data:
      mode: away
    ```

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
- Create sensors for device status and measurements
- Register the change_mode service

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
3. Common issues:
   - Authentication failures: Verify your email and password
   - Connection issues: Check your network connection
   - Missing updates: The WebSocket connection might be interrupted
   - Sensor state issues: Check if the device is reachable and sending data
   - Service call failures: Verify the entity ID and mode parameter

## Development Status

This integration is currently in development. Future enhancements planned:
- Additional sensor types for various device metrics
- Enhanced error handling and recovery
- Support for multiple devices
- More detailed alarm state reporting
- Historical data analysis features 