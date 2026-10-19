"""Standard-library Linux inventory. Reads only; no device or driver changes."""
import os
import platform
import re
import subprocess
import time
from pathlib import Path

MAC = r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}'

def redact(text):
    return re.sub(MAC, '[device address]', text)

class Runner:
    def __init__(self, budget=35):
        self.deadline = time.monotonic() + budget
    def __call__(self, args):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return 'UNKNOWN: report time budget reached; refresh to retry.'
        try:
            p = subprocess.run(args, capture_output=True, text=True,
                               timeout=min(4, remaining), env={**os.environ, 'LC_ALL': 'C'})
            output = (p.stdout + p.stderr).strip()
            return output if p.returncode == 0 else f'UNKNOWN: exit {p.returncode}: {output}'
        except subprocess.TimeoutExpired:
            return 'UNKNOWN: command timed out.'
        except OSError as exc:
            return f'UNKNOWN: command unavailable: {exc}'

def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return 'unknown'

def parse_inputs(text):
    found = []
    for block in text.split('\n\n'):
        name = re.search(r'N: Name="(.*?)"', block)
        ids = re.search(r'Bus=(\w+) Vendor=(\w+) Product=(\w+)', block)
        handlers = re.search(r'H: Handlers=(.*)', block)
        if not name or not ids:
            continue
        # Include unmapped joystick nodes and common controller names, not keyboards by vendor alone.
        if not (re.search(r'\bjs\d+\b', handlers[1] if handlers else '') or
                re.search(r'xbox|playstation|dualsense|dualshock|gamepad|controller', name[1], re.I)):
            continue
        found.append({'name': name[1], 'bus': ids[1], 'vendor': ids[2], 'product': ids[3],
                      'transport': {'0003': 'USB', '0005': 'Bluetooth'}.get(ids[1], 'other/unknown'),
                      'handlers': handlers[1].strip() if handlers else 'unknown'})
    return found

def adapter_inventory(root='/sys/class/bluetooth'):
    result = []
    for adapter in sorted(Path(root).glob('hci*')):
        if not re.fullmatch(r'hci\d+', adapter.name):
            continue
        device = (adapter / 'device').resolve()
        usb_id = 'not exposed (possibly non-USB adapter)'
        for parent in [device, *device.parents]:
            vendor, product = read(parent/'idVendor'), read(parent/'idProduct')
            if vendor != 'unknown' and product != 'unknown':
                usb_id = vendor + ':' + product
                break
        driver = device/'driver'
        result.append(f'{adapter.name}: USB ID {usb_id}; driver {driver.resolve().name if driver.exists() else "unknown"}')
    return result

def advice(text, inputs):
    notes = []
    if 'Soft blocked: yes' in text or 'Hard blocked: yes' in text:
        notes.append('Bluetooth is radio-blocked. Inspect airplane mode / physical radio switch in Ubuntu Settings.')
    if 'Powered: no' in text:
        notes.append('An adapter is powered off. Enable the intended adapter in Settings; keep the PS3 adapter active.')
    if 'No default controller available' in text:
        notes.append('BlueZ has no default adapter. Check adapter detection and Bluetooth service status below.')
    if 'Connected: no' in text:
        notes.append('A known controller is disconnected. Unplug Xbox USB, hold its Pair button until flashing rapidly, then pair in Settings.')
    if 'Connected: yes' in text:
        notes.append('A Bluetooth controller reports connected. Compare its name with the kernel input list; this alone does not verify button input.')
    if any(i['transport'] == 'USB' and 'xbox' in i['name'].lower() for i in inputs):
        notes.append('Xbox USB input is present. Unplug the cable to test wireless independently.')
    notes += ['For Series X|S: adapter must support Bluetooth LE. A working PS3 connection does not prove LE support.',
              'No kernel gamepad after successful pairing: inspect UHID/driver availability and BlueZ logs. Kernel input present but no live display: investigate SDL mapping/access.',
              'UNKNOWN means a check failed or is unavailable, not proof of missing hardware. See PAIRING.md for the next steps.']
    return notes

def report(runner=None, proc='/proc/bus/input/devices', sysroot='/sys/class/bluetooth'):
    run = runner or Runner()
    inputs_raw = read(proc)
    inputs = parse_inputs(inputs_raw)
    lines = ['HBOMB Controller Hub 0.3.0 — read-only Linux report',
             'Addresses hidden; device names may be personal. No pairing/settings/driver changes.',
             f'Kernel: {platform.release()}', '', 'LINUX INPUT DEVICES (snapshot; not an input test)']
    lines += [f'{i["name"]}: {i["transport"]}; ID {i["vendor"]}:{i["product"]}; {i["handlers"]}' for i in inputs]
    if not inputs:
        lines.append('Input inventory unavailable.' if inputs_raw == 'unknown' else 'No controller-like kernel input nodes found.')
    adapters_sys = adapter_inventory(sysroot)
    lines += ['', 'ADAPTER HARDWARE', *adapters_sys]
    if not adapters_sys:
        lines.append('No hci adapter visible in sysfs; check BlueZ output below.')
    evidence = []
    def section(title, args):
        value = run(args)
        evidence.append(value)
        lines.extend(['', title, value or '(empty output)'])
        return value
    section('RADIO BLOCKS', ['rfkill', 'list', 'bluetooth'])
    section('BLUETOOTH SERVICE', ['systemctl', 'is-active', 'bluetooth'])
    section('BLUEZ VERSION', ['bluetoothctl', '--version'])
    adapters = section('ALL BLUEZ ADAPTERS', ['bluetoothctl', 'list'])
    addresses = re.findall(r'^Controller ('+MAC+r') ', adapters, re.M)
    for address in addresses[:4]:
        section('ADAPTER STATE', ['bluetoothctl', 'show', address])
    if not addresses:
        section('DEFAULT ADAPTER STATE', ['bluetoothctl', 'show'])
    devices = section('KNOWN DEVICES (default adapter only; not a discovery scan)', ['bluetoothctl', 'devices'])
    matches = re.findall(r'^Device ('+MAC+r') (.+)$', devices, re.M)
    candidates = [(a,n) for a,n in matches if re.search('xbox|controller|dualsense|playstation|gamepad', n, re.I)]
    for address, name in candidates[:6]:
        section('DEVICE: '+name, ['bluetoothctl', 'info', address])
    if len(addresses)>4 or len(candidates)>6:
        lines.append('Inventory truncated to 4 adapters / 6 controller-like devices.')
    lines += ['', 'KERNEL MODULE AVAILABILITY (not proof of binding to a device)']
    for module in ('uhid', 'hid_xpadneo', 'hid_microsoft', 'xpad', 'hid_sony', 'hid_playstation'):
        section(module, ['modinfo', '-F', 'filename', module])
    lines += ['', 'NEXT CHECKS', *advice('\n'.join(evidence), inputs)]
    return redact('\n'.join(lines))

if __name__ == '__main__':
    print(report())
