# Leakomatic Integration for Home Assistant

This integration allows you to connect your Leakomatic water leak sensors to Home Assistant.

## Supported Languages

This integration supports the following languages:
- English (en)
- Swedish (sv)

The integration will automatically use the language that matches your Home Assistant language settings.

## Debug Logging

To enable debug logging for this integration, add the following to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.leakomatic: debug
```

After adding this configuration, restart Home Assistant to apply the changes. Debug logs will appear in your Home Assistant logs and can be viewed in the Developer Tools > Logs section of the Home Assistant UI.

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Leakomatic"
4. Enter your email and password
5. Click "Submit"

## Troubleshooting

If you encounter any issues with the integration, please enable debug logging as described above and check the logs for detailed information about what might be going wrong. 