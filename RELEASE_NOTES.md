# Release Notes - Version 0.2.1

A bug fix release. The complete list of changes is in the [changelog](CHANGELOG.md).

## Fixed

- **Leak test attributes keep the app's units.** After a setting was changed in Leakomatic's app, the attributes of *Flow test*, *Quick test* and *Tightness test* switched to seconds (for example the flow test's home duration 20 became 1200) until the next restart. They now always use the app's units (minutes, hours, days), and the quick test's index limit is rounded (0.7, not 0.699999988079071).

## Installation

1. Update through HACS, or copy `custom_components/leakomatic` from this release into your Home Assistant configuration.
2. Restart Home Assistant.
