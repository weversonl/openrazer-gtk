# OpenRazerGTK

A native GTK4/Libadwaita control panel for Razer peripherals, built on top of [OpenRazer](https://openrazer.github.io/).

## Motivation

I wanted to control my Razer mouse and charging dock without leaving the GTK/GNOME environment — no Electron, no Wine, nothing that looks out of place next to the rest of my desktop. OpenRazerGTK follows GNOME HIG conventions (headerbar, sidebar navigation, boxed lists, system accent colors, light/dark theming) instead of porting the Razer Synapse/Polychromatic UI as-is.

The whole interface is **capability-driven**: nothing is shown unconditionally. Every section (DPI, battery, lighting zones, etc.) is derived at runtime from what the connected device actually reports through `python-openrazer` — if a capability isn't there, the section simply doesn't exist, no placeholders or disabled states.

## Features

- **DPI control** — discrete stage tables or continuous DPI (with independent X/Y axes where supported), plus a dedicated editor for onboard DPI stages
- **Poll rate**
- **Lighting** — effects, color, and brightness for the device's main light or LED zones
- **Battery & power** — charge level with a charging indicator, idle-sleep timer, low-battery threshold
- **Local presets** — save/apply/undo combinations of the above (DPI, poll rate, lighting) as app-local snapshots; these are not on-board hardware profiles, since `python-openrazer` doesn't expose an API for those
- **Per-device display name and image** — purely cosmetic overrides, stored locally, the device itself is never touched
- **Tray icon and autostart**
- Automatic light/dark theme and PT-BR/EN-US language, following system settings

## Requirements

- `openrazer-daemon` running (`systemctl --user status openrazer-daemon` or equivalent)
- `python-openrazer` installed
- GTK 4 + Libadwaita ≥ 1.4 and PyGObject

## Running in development

No install needed:

```sh
python -m razer_gtk
```

## Installing a launcher

To add OpenRazerGTK to your application launcher (icon + `.desktop` entry, user-level, no root needed):

```sh
./install.sh
```

## Status

**Work in progress.** Built and tested primarily against a Razer Viper Ultimate (Wireless) and its charging dock — other devices may behave differently or hit rough edges, since `python-openrazer`'s reported capabilities vary a lot across the Razer lineup. Bug reports welcome.
