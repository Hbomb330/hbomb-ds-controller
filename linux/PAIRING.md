# Xbox Bluetooth checklist

Your previous tests: PS3 Bluetooth worked; Xbox Series S worked by USB. Those are user-reported results from the earlier build. The adapter, Ubuntu release, exact controller label and pairing failure are still unknown. This build collects evidence; it does not claim to fix the connection.

## First try

1. Leave the existing PS3 pairing intact. Do not remove it or reset the adapter.
2. Run the app's Bluetooth report before changing anything. Check adapter power, radio blocks and controller Connected/Paired state.
3. Disconnect the Xbox USB cable. Charge the controller / fit fresh batteries. Turn it on and hold the Pair button until the Xbox light flashes rapidly.
4. Open Ubuntu Bluetooth Settings and pair the Xbox controller. Keep any console it reconnects to switched off during this test.
5. Return to the app, click Scan, move sticks and press buttons. Run the report again. A Bluetooth connection is not proof that input works.
6. If pairing fails, record the exact error and share the saved report. Review device names first; addresses are redacted but names may identify you.

## Interpret the evidence

| Observation | Next step |
|---|---|
| No hci adapter / no default controller | Check adapter is physically detected; inspect service and rfkill output. A command failure is not proof hardware is absent. |
| Radio blocked | Inspect Ubuntu airplane mode and any physical radio switch. Hard blocks need hardware/firmware attention. |
| Powered: no | Enable the intended Bluetooth adapter in Settings. Avoid toggling the adapter currently serving PS3 during a session. |
| Xbox never appears | Check pairing mode, battery and Bluetooth LE capability. The report lists known devices, not nearby undiscovered ones; use Settings for discovery. |
| Paired: yes, Connected: no | Try Connect in Settings. If still failing, record the error before removing only the Xbox pairing. |
| Connected: yes, no matching kernel input | Check UHID availability, BlueZ and controller driver logs; compare controller name/IDs. Bluetooth devices on a non-default adapter need manual inspection. |
| Kernel input present, no live gamepad | SDL mapping or user access may be the issue. Kernel inventory includes likely controllers even if SDL cannot map them. Do not run the GUI as root or broadly change input permissions. |
| Connection repeatedly drops | Check battery, interference and firmware; capture logs. Do not start with global Bluetooth configuration hacks. |

For extra diagnostics, these commands only read information:

```bash
cat /etc/os-release
bluetoothctl list
btmgmt info
journalctl -b -u bluetooth --no-pager -n 100
journalctl -b -k --no-pager -n 150
```

`btmgmt info` may require elevated read access. Look for `le` in supported settings for the selected adapter; lack of access means unknown. Logs may contain addresses and personal information: inspect/redact before sharing. The app does not collect or upload journals.

With multiple adapters, `bluetoothctl devices/info` reflects its default adapter. To inspect another, open interactive `bluetoothctl`, use `list`, `select ADAPTER_ADDRESS`, then `devices` and `info DEVICE_ADDRESS`. Use actual addresses shown locally, not the redacted report placeholders. Exit with `quit`. The app never changes the default adapter.

## Models and driver routes

| Controller | Wireless method | Linux route |
|---|---|---|
| Xbox Series X/S (standard model 1914) | Bluetooth LE or Xbox Wireless | Test stock Ubuntu first; optional xpadneo for Bluetooth. Adapter must support LE. |
| Xbox One S-era model 1708 / Elite Series 2 | Bluetooth or Xbox Wireless | Stock kernel support varies; xpadneo supports Bluetooth. Firmware can change the Bluetooth protocol. |
| Original Xbox One models 1537/1697 / Elite Series 1 | Xbox Wireless, not Bluetooth | USB or a compatible Xbox Wireless adapter; investigate xone separately. |
| Xbox 360 wireless | Proprietary receiver, not Bluetooth | Xbox 360 receiver with xpad; charge cable does not make a wireless pad a wired controller. |
| PS3 | USB / Bluetooth | Existing Linux hid_sony / BlueZ path; retain the pairing that already works. |
| PS5 DualSense | USB / Bluetooth | Linux hid_playstation; live controls depend on SDL mapping. |
| Third-party Xbox-style pads | Varies | Check the manufacturer's exact model and selected mode; Xbox appearance does not prove Bluetooth support. |

The printed label is more reliable than a generic Bluetooth name. Firmware can cause different Xbox models to expose shared product IDs; this app does not guess an exact model from that ID.

`xpad` is principally the USB / Xbox 360 receiver route. `xpadneo` is a separate Bluetooth driver. `xone` targets wired and proprietary Xbox Wireless accessories, not Bluetooth pairing. Do not install all three as a blanket fix. Inspect current kernel/BlueZ versions and the report first. External DKMS drivers require matching headers and may need Secure Boot signing; installation is deliberately not automated.

If firmware is implicated, use Microsoft's Xbox Accessories app on Windows or an Xbox console, following its instructions over USB. Following an update, forget/re-pair only the Xbox controller if necessary; preserve PS3. Avoid editing global BlueZ settings or disabling security based on old generic workarounds.

## Primary references checked 2026-10-19

- xpadneo model support, BLE and UHID requirements: https://atar-axis.github.io/xpadneo/
- xpadneo troubleshooting and firmware notes: https://github.com/atar-axis/xpadneo/blob/master/docs/TROUBLESHOOTING.md
- xone scope: https://github.com/medusalix/xone
- Kernel xpad documentation: https://www.kernel.org/doc/html/latest/input/devices/xpad.html
- Kernel PlayStation implementation: https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c
