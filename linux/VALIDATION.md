# 0.3.0 validation — 2026-10-19

Passed in the Linux build environment:
- 16 Python unittest cases, including prior profile/deadzone tests.
- Python compilation and launch.sh shell syntax.
- Actual pygame 2.6.1 / SDL dummy-video demo: 10 frames rendered and clean exit.
- Headless CLI report with missing Bluetooth utilities and no controllers: clean exit, unknown checks reported.

This environment is not your Ubuntu computer. No Bluetooth radio, PS3, PS5 or Xbox was exercised. Fixture tests do not establish pairing or input compatibility. The GitHub workflow repeats hardware-free checks on Ubuntu when run; its result must be checked separately.

Next physical test: leave PS3 paired; disconnect Xbox USB; pair Xbox in Ubuntu Settings; use Scan and Bluetooth report. Confirm PS3 still works and capture the Xbox pairing error if present. Test sticks/buttons, reconnect, rumble and PS5 separately.
