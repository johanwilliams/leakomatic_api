# Leakomatic Integration for Home Assistant

This integration allows you to connect your Leakomatic water leak sensors to Home Assistant.

## Features

- Real-time updates via WebSocket connection
- Device mode monitoring (Home/Away/Pause)
- Alarm status monitoring
- Device information display (model, software version, location)
- Automatic reconnection handling

## Supported Languages

This integration supports the following languages:
- English (en)
- Swedish (sv)

The integration will automatically use the language that matches your Home Assistant language settings.

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
- Set up real-time monitoring
- Create sensors for device status

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

## Development Status

This integration is currently in development. Future enhancements planned:
- Additional sensor types for various device metrics
- Configuration options for update intervals
- Enhanced error handling and recovery
- Support for multiple devices 