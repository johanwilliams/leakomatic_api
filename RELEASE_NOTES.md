# Release Notes - Version 0.1.6

Bug-fix release.

## Fixed

- **CLEAR alarm level logged as unknown**  
  A valid CLEAR alarm level (`0`) arriving over the websocket was compared with the wrong type and logged as `Unknown alarm level received: 0` instead of clearing the alarm sensor. It is now handled correctly.

- **Websocket reconnection and stale connections**  
  Successful reconnections are now recognised, so a normal reconnect (for example after the server's scheduled disconnect) no longer pushes the retry strategy towards hour-long or indefinite waits. A connection that stays silent for 120 seconds is treated as dead and reconnected.

Thanks to @skallan for both fixes.

## Installation

1. Update the integration through HACS or copy the updated `custom_components/leakomatic` files manually.
2. Restart Home Assistant.

## Migration notes

No breaking changes.

## Upcoming

Changes merged after 0.1.6 are listed under *Unreleased* in the [changelog](CHANGELOG.md).
