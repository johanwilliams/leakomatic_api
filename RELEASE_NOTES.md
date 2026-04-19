# Release Notes - Version 0.1.5

## Fixed

- **Home Assistant Core 2026.4+ services loader**  
  Newer Home Assistant versions strictly validate `services.yaml`. An empty file (or YAML that parses to `null`) caused a `NoneType: None` error in the core log on startup. This release adds a proper `services.yaml` that documents the `leakomatic.change_mode` service (aligned with the select-based mode control and the service still registered by the integration).

## Installation

1. Update the integration through HACS or copy the updated `custom_components/leakomatic` files manually.
2. Restart Home Assistant.

## Migration notes

No breaking changes. After upgrade, the core log should no longer show the services.yaml load error for this integration.

## Previous highlights

See the [changelog](CHANGELOG.md) for earlier versions. Version 0.1.4 addressed Home Assistant scheduling API compatibility; 0.1.3 included UI and logging refinements.
