"""Read-only Bluetooth checks; never pairs devices or changes drivers."""
import re
import shutil
import subprocess


def run_command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        output = (result.stdout + result.stderr).strip()
        return output or f'Command returned {result.returncode} with no output.'
    except subprocess.TimeoutExpired:
        return 'Command timed out. Bluetooth service may be unavailable.'
    except OSError as exc:
        return f'Command unavailable: {exc}'


def redact(text):
    return re.sub(r'\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b', '[device address]', text)


def bluetooth_report():
    lines = ['HBOMB Bluetooth diagnostics — read-only', '',
             'This report distinguishes OS Bluetooth status from SDL gamepad detection.',
             'Device addresses are hidden. Device names may still be personal.', '']
    if not shutil.which('bluetoothctl'):
        return '\n'.join(lines + ['bluetoothctl is missing. Use Ubuntu Bluetooth Settings to check pairing.'])
    lines.extend(['ADAPTER', redact(run_command(['bluetoothctl', 'show'])), '', 'KNOWN DEVICES'])
    devices = run_command(['bluetoothctl', 'devices'])
    lines.append(redact(devices))
    candidates = []
    for line in devices.splitlines():
        match = re.match(r'Device ([0-9A-Fa-f:]{17}) (.+)', line)
        if match and any(word in match[2].lower() for word in ('xbox', 'controller', 'dualsense', 'playstation', 'gamepad')):
            candidates.append(match)
    for match in candidates[:4]:
        lines.extend(['', match[2], redact(run_command(['bluetoothctl', 'info', match[1]]))])
    lines.extend(['', 'NEXT CHECK',
                  'Unplug the Xbox USB cable before testing Bluetooth.',
                  'Put the controller into pairing mode, then pair in Ubuntu Bluetooth Settings.',
                  'If Connected is no: resolve pairing first.',
                  'If Connected is yes but the app sees no gamepad: input/SDL detection needs investigation.',
                  'Press Scan in the app after pairing. No drivers or settings were changed.'])
    return '\n'.join(lines)


def open_settings():
    candidates = [('gnome-control-center', 'bluetooth'), ('blueman-manager',)]
    for command in candidates:
        if shutil.which(command[0]):
            with open('/dev/null', 'wb') as sink:
                subprocess.Popen(command, stdout=sink, stderr=sink, start_new_session=True)
            return 'Bluetooth settings requested. Pair there, then return and press Scan.'
    return 'Open Bluetooth settings from your desktop Settings application.'
