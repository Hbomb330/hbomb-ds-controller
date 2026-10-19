# HBOMB Controller Hub 0.3.0 — Ubuntu test build

A native desktop controller diagnostic app targeting PS5 DualSense and Xbox gamepads exposed by Ubuntu and SDL. This is a source-based prototype, not a prebuilt .deb/AppImage or a replacement controller driver.

## Start on Ubuntu

1. Extract this ZIP.
2. Open a terminal inside the extracted folder.
3. Install the dependencies from Ubuntu's repositories:

```bash
sudo apt update
sudo apt install python3 python3-pygame bluez rfkill kmod
```

4. Run:

```bash
bash launch.sh
```

Plug your controller in with a data-capable USB cable first. For Bluetooth, pair it in Ubuntu Settings before launching. Click Scan after connecting; Next cycles through supported devices. No sudo is needed to run the app.

For an animated preview with no controller:

```bash
bash launch.sh --demo
```

## New in 0.3

- Read-only Linux input inventory identifies USB vs Bluetooth bus and input handlers, including likely controllers absent from SDL mapping.
- Lists Bluetooth adapters, USB hardware IDs when exposed, radio blocks, service state, BlueZ version and module availability.
- Reports default-adapter controller pairing/connection state with practical next checks; see [PAIRING.md](PAIRING.md).
- Background diagnostics have a 35-second subprocess budget. Failures remain UNKNOWN, not false claims of missing hardware.
- No driver installation, pairing deletion, adapter switching or system configuration changes.
- Existing display, rumble button, profiles and PS3 input path are retained from 0.2.0.
- Save report writes locally to `~/.config/hbomb-controller-hub/bluetooth-report.txt` (or `$XDG_CONFIG_HOME`). Device addresses are hidden; review names before sharing.

Run diagnostics without pygame or a desktop:

```bash
python3 controller_hub.py --report
```

Optional desktop shortcut: `python3 install-launcher.py`. Keep the extracted folder in place. Remove `~/.local/share/applications/hbomb-controller-hub.desktop` to uninstall the shortcut.

## Your reported device results

You reported that the previous build worked with a PS3 controller over Bluetooth and an Xbox Series S controller over USB. Xbox Bluetooth and PS5 remain unverified. These are user-reported results for your setup, not certification for every controller.

For the Xbox wireless test, unplug USB, open Bluetooth settings and put the controller in pairing mode. After pairing, return and press Scan. If it is still missing, run Bluetooth report and inspect Connected status. This build adds diagnostics; it does not claim to fix the wireless connection.

## Included

- Shared Xbox/PlayStation labels for 15 buttons including D-pad and stick clicks.
- Two live stick plots: gray raw position and blue deadzone-adjusted preview.
- Live left/right trigger bars.
- Adjustable radial deadzone from 0% to 40%.
- Saved deadzone profiles by SDL device GUID, loaded on connection.
- Short, user-triggered 350 ms vibration test where SDL and the driver support it.
- Hotplug handling, device cycling, resizable window and explicit demo mode.

Profiles are stored in `$XDG_CONFIG_HOME/hbomb-controller-hub/profiles.json`, or `~/.config/hbomb-controller-hub/profiles.json`. Identical devices sharing a GUID share a profile; USB and Bluetooth GUIDs may differ. Delete this file to reset settings.

## Scope and compatibility

Deadzone settings affect this app's blue preview only. Version 0.3 does NOT remap game inputs, create a virtual Xbox controller, change Steam settings, install drivers, pair Bluetooth devices, or control adaptive triggers, LEDs, gyro, touchpad or battery reporting. There is no network functionality in the application.

Actual support depends on the Ubuntu kernel, SDL mapping database, controller model and transport. In particular, do not assume an Xbox wireless USB adapter behaves like a wired or Bluetooth connection. A controller absent from SDL's mapped-controller list is not opened by this build. Do not loosen `/dev/input` permissions or run the app as root as a workaround.

## First physical-device test

- Start with USB and confirm the device name.
- Check each face button, D-pad, shoulder, stick click and menu button.
- Move both sticks through full travel; release and inspect center drift.
- Pull both triggers and confirm 0–100% values.
- Try Test rumble; lack of vibration may be a driver/transport limitation.
- Save a deadzone, restart and confirm it loads.
- Unplug/reconnect and check recovery; repeat using paired Bluetooth.
- Repeat with the other controller model.

## Validation

Hardware-free tests cover transport parsing, malformed/unknown devices, multiple adapters, USB adapter identification, radio/power guidance, redaction, read-only command boundaries, missing commands, timeouts, report budget and existing deadzone/profile behavior.

```bash
python3 -m unittest discover -v
python3 -m compileall -q .
bash -n launch.sh
SDL_VIDEODRIVER=dummy python3 controller_hub.py --demo --smoke-test
```

The GUI smoke test requires pygame; unit tests and `--report` do not. The included GitHub Actions workflow runs these checks on Ubuntu. See VALIDATION.md for this build's actual results.

Physical acceptance still required: PS3 Bluetooth regression check; Xbox pairing without USB; buttons/sticks/triggers; reconnect after sleep/reboot; simultaneous controllers; PS5 USB/Bluetooth; rumble. No fixture or demo test proves wireless connectivity on your computer.

## Implementation reference

Uses pygame's SDL controller API for normalized input and rumble:
https://www.pygame.org/docs/ref/sdl2_controller.html

## Removal

Delete the extracted app folder. Optionally delete the profile folder above. No services, udev rules or background startup entries are installed.
