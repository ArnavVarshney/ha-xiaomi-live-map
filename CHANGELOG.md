# Changelog

## 1.0.1

- Brand icon shipped with the integration (shown in Home Assistant 2026.3 and newer).

## 1.0.0

First public release.

- UI setup that picks a robot from Xiaomi Cloud Map Extractor, with optional vacuum, job and map-name entities and
  adjustable update intervals.
- Live map streamed over the websocket API: a full snapshot on subscribe, then only new path points.
- Card served by the integration and listed in the card picker, with a visual editor.
- Vacuum line and mop band, rooms, carpets, virtual walls, restricted zones, dock and robot.
- The last clean is kept after docking and survives restarts.
- Room picking in the card, or through `input_boolean` helpers, and a two-tap **▶ Clean** button that runs a script
  with the selected room ids.
- Clear errors for unsupported models, extractor versions and expired sessions, and diagnostics without coordinates.
