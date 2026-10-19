#!/usr/bin/env python3
"""HBOMB Controller Hub: local controller diagnostics. No system input injection."""
import argparse
import json
import math
import os
import queue
import threading
import textwrap
from bluetooth_diagnostics import open_settings
from linux_inventory import report as bluetooth_report
from pathlib import Path

VERSION = '0.3.0'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'hbomb-controller-hub' / 'profiles.json'


def deadzone(x, y, amount):
    magnitude = math.hypot(x, y)
    if magnitude <= amount:
        return 0.0, 0.0
    scale = min(1.0, (magnitude - amount) / (1.0 - amount)) / magnitude
    return x * scale, y * scale


def load_profiles(path=CONFIG):
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError('Profiles must be an object')
        for key, value in data.items():
            if not isinstance(value, dict) or not isinstance(value.get('deadzone'), (int, float)) or not 0 <= value['deadzone'] <= 0.4:
                raise ValueError('Invalid deadzone profile')
        return data, ''
    except FileNotFoundError:
        return {}, ''
    except (OSError, ValueError, TypeError) as exc:
        return {}, f'Profile read failed: {exc}'


def save_profiles(data, path=CONFIG):
    path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix='profiles-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true', help='Print read-only diagnostics without pygame')
    parser.add_argument('--demo', action='store_true', help='Animated simulated inputs, no hardware required')
    parser.add_argument('--smoke-test', action='store_true', help='Render 10 frames and exit')
    parser.add_argument('--screenshot', help='Save last rendered frame')
    args = parser.parse_args()
    if args.report:
        print(bluetooth_report())
        return
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    os.environ.setdefault('SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS', '1')
    import pygame as pg
    from pygame._sdl2 import controller as pad
    pg.display.init()
    pg.font.init()
    pg.joystick.init()
    pad.init()
    screen = pg.display.set_mode((1040, 830), pg.RESIZABLE)
    pg.display.set_caption(f'HBOMB Controller Hub • Ubuntu • {VERSION}')
    canvas = pg.Surface((1040, 830))
    clock = pg.time.Clock()
    fonts = {s: pg.font.SysFont('DejaVu Sans', s) for s in (13, 16, 20, 28, 38)}
    bg, panel, blue, white, muted = '#090f1d', '#121e31', '#47c9ff', '#eef5ff', '#8fabc6'
    profiles, warning = load_profiles()
    device, identity, name, dz = None, '', 'No controller connected', .12
    status = warning or 'Connect by USB, or pair in Ubuntu Bluetooth settings. Then press Scan.'
    scan_index, frames, running = 0, 0, True
    buttons = []
    diagnostic_results = queue.Queue()
    diagnostic_busy = False
    diagnostic_text = ''
    overlay = False
    scroll = 0

    def diagnostic_worker():
        try:
            diagnostic_results.put(bluetooth_report())
        except Exception as exc:
            diagnostic_results.put(f'Diagnostics failed: {exc}')

    def text(value, x, y, size=16, color=white):
        canvas.blit(fonts[size].render(str(value), True, color), (x, y))

    def box(rect, color=panel):
        pg.draw.rect(canvas, color, rect, border_radius=14)

    def button(label, rect, action):
        box(rect, '#20344d')
        text(label, rect[0]+12, rect[1]+10)
        buttons.append((pg.Rect(rect), action))

    def close_device():
        nonlocal device
        if device:
            try:
                device.stop_rumble()
                device.quit()
            except pg.error:
                pass
        device = None

    def scan(next_device=False):
        nonlocal device, identity, name, dz, status, scan_index
        close_device()
        identity, name = '', 'No controller connected'
        try:
            pg.event.pump()
            candidates = [i for i in range(pad.get_count()) if pad.is_controller(i)]
            if not candidates:
                status = 'No SDL-mapped gamepad found. Check USB/Bluetooth, then Scan again.'
                return
            scan_index = (scan_index + int(next_device)) % len(candidates)
            device = pad.Controller(candidates[scan_index])
            name = device.name
            identity = device.as_joystick().get_guid()
            dz = profiles.get(identity, {}).get('deadzone', .12)
            status = f'Connected • {len(candidates)} supported device(s) • Profile uses controller GUID'
        except pg.error as exc:
            close_device()
            status = f'Controller access failed: {exc}'

    if not args.demo:
        scan()
    try:
        while running:
            actions = []
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    if overlay:
                        overlay = False
                    else:
                        running = False
                elif event.type == pg.MOUSEWHEEL and overlay:
                    scroll = max(0, min(max(0, sum(max(1, len(textwrap.wrap(line, width=112))) for line in diagnostic_text.splitlines())-24), scroll-event.y*3))
                elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                    w, h = screen.get_size()
                    point = (event.pos[0]*1040/w, event.pos[1]*830/h)
                    actions.extend(action for rect, action in buttons if rect.collidepoint(point))
                elif event.type in (pg.CONTROLLERDEVICEADDED, pg.CONTROLLERDEVICEREMOVED):
                    if not args.demo:
                        scan()
            try:
                diagnostic_text = diagnostic_results.get_nowait()
                diagnostic_busy = False
                overlay, scroll = True, 0
                status = 'Bluetooth report ready. Scroll to read; Escape closes the report.'
            except queue.Empty:
                pass
            for action in actions:
                if action == 'bluetooth':
                    try:
                        status = open_settings()
                    except OSError as exc:
                        status = f'Could not open settings: {exc}'
                elif action == 'diagnose' and not diagnostic_busy:
                    diagnostic_busy = True
                    status = 'Checking Bluetooth in the background…'
                    threading.Thread(target=diagnostic_worker, daemon=True).start()
                elif action == 'close_report':
                    overlay = False
                elif action == 'save_report':
                    try:
                        destination = CONFIG.parent / 'bluetooth-report.txt'
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(diagnostic_text)
                        status = 'Report saved in your hbomb-controller-hub config folder.'
                    except OSError as exc:
                        status = f'Report save failed: {exc}'
                if action in ('scan', 'next'):
                    if args.demo:
                        status = 'Demo inputs are simulated. Restart without --demo to use a controller.'
                    else:
                        scan(action == 'next')
                elif action in ('minus', 'plus'):
                    dz = round(max(0, min(.4, dz + (.02 if action == 'plus' else -.02))), 2)
                elif action == 'save':
                    if not identity or args.demo:
                        status = 'Connect a real controller before saving a profile.'
                    else:
                        profiles[identity] = {'deadzone': dz, 'name': name}
                        try:
                            save_profiles(profiles)
                            status = 'Profile saved. Deadzone affects the preview in this app only.'
                        except OSError as exc:
                            status = f'Could not save profile: {exc}'
                elif action == 'rumble':
                    if device and not args.demo:
                        try:
                            ok = device.rumble(.35, .35, 350)
                            status = '350 ms rumble requested.' if ok else 'Rumble unavailable with this controller/driver.'
                        except pg.error as exc:
                            status = f'Rumble failed: {exc}'
                    else:
                        status = 'Rumble requires a connected physical controller.'
            axes, pressed = [0.0]*6, [False]*15
            if args.demo:
                t = frames / 60
                axes = [math.sin(t)*.65, math.cos(t)*.65, math.sin(t*.7)*.18, math.cos(t*.7)*.18, (math.sin(t)+1)/2, (math.cos(t)+1)/2]
                pressed[int(t*2)%15] = True
                name = 'DEMO • simulated PS5 / Xbox input'
            elif device:
                try:
                    if not device.attached():
                        raise pg.error('Controller disconnected')
                    axes = [max(-1, min(1, device.get_axis(i)/32767)) for i in range(6)]
                    pressed = [device.get_button(i) for i in range(15)]
                except pg.error as exc:
                    close_device()
                    identity, name = '', 'Controller disconnected'
                    status = f'{exc}. Reconnect and press Scan.'
            canvas.fill(bg)
            buttons = []
            text('HBOMB', 30, 22, 38, blue)
            text('CONTROLLER HUB', 200, 34, 20)
            text('UBUNTU / LINUX     •     TEST BUILD 0.3.0', 620, 38, 16, muted)
            box((30, 90, 980, 90))
            text(name[:68], 50, 107, 20)
            text('PS3 / PS5 + Xbox  |  USB / paired Bluetooth  |  SDL input', 50, 143, 13, muted)
            button('Scan', (790, 111, 90, 44), 'scan')
            button('Next', (892, 111, 95, 44), 'next')
            for j, title in enumerate(('LEFT STICK', 'RIGHT STICK')):
                left = 30+j*330
                box((left, 200, 310, 270))
                text(title, left+20, 218, 16, muted)
                center = (left+155, 337)
                pg.draw.circle(canvas, '#0a1424', center, 76)
                pg.draw.circle(canvas, '#294561', center, 76, 2)
                pg.draw.circle(canvas, '#294561', center, max(1, int(dz*76)), 1)
                pg.draw.line(canvas, '#294561', (center[0]-76, center[1]), (center[0]+76, center[1]))
                pg.draw.line(canvas, '#294561', (center[0], center[1]-76), (center[0], center[1]+76))
                x, y = axes[j*2:j*2+2]
                px, py = deadzone(x, y, dz)
                pg.draw.circle(canvas, muted, (int(center[0]+x*76), int(center[1]+y*76)), 5)
                pg.draw.circle(canvas, blue, (int(center[0]+px*76), int(center[1]+py*76)), 9, 2)
                text(f'Raw  X {x:+.2f}   Y {y:+.2f}', left+42, 423, 16)
                text('Gray: raw   Blue: deadzone preview', left+30, 449, 13, muted)
            box((690, 200, 320, 270))
            text('TRIGGERS', 710, 218, 16, muted)
            for i, label in enumerate(('LT / L2', 'RT / R2')):
                y = 265+i*84
                value = max(0, axes[4+i])
                text(label, 710, y)
                text(f'{value:.0%}', 930, y)
                pg.draw.rect(canvas, '#26394f', (710, y+30, 278, 15), border_radius=7)
                if value > 0:
                    pg.draw.rect(canvas, blue, (710, y+30, int(278*value), 15), border_radius=7)
            labels = ['A / Cross', 'B / Circle', 'X / Square', 'Y / Triangle', 'Back / Create', 'Guide / PS', 'Start / Options', 'LS / L3', 'RS / R3', 'LB / L1', 'RB / R1', 'D-pad Up', 'D-pad Down', 'D-pad Left', 'D-pad Right']
            for i, label in enumerate(labels):
                x, y = 30+(i%5)*198, 490+(i//5)*40
                box((x, y, 188, 32), blue if pressed[i] else panel)
                text(label, x+10, y+6, 13, bg if pressed[i] else muted)
            text(f'Preview deadzone: {dz:.0%}', 30, 631, 16)
            button('−', (260, 620, 46, 42), 'minus')
            button('+', (314, 620, 46, 42), 'plus')
            button('Save profile', (380, 620, 155, 42), 'save')
            button('Test rumble', (550, 620, 155, 42), 'rumble')
            text('Preview only • no game remapping', 725, 633, 13, muted)
            button('Bluetooth settings', (30, 681, 210, 42), 'bluetooth')
            button('Checking…' if diagnostic_busy else 'Bluetooth report', (255, 681, 210, 42), 'diagnose')
            text('Xbox wireless: unplug USB, pair in Settings, then Scan.', 485, 695, 13, muted)
            text(status[:115], 30, 753, 13, blue)
            text('Local diagnostics • No administrator access • Escape to close', 30, 788, 13, muted)
            if overlay:
                box((20, 80, 1000, 650), '#18283e')
                text('BLUETOOTH REPORT', 42, 98, 20, blue)
                text('Mouse wheel to scroll • Escape to close • Addresses hidden', 42, 132, 13, muted)
                lines = []
                for line in diagnostic_text.splitlines():
                    lines.extend(textwrap.wrap(line, width=112) or [''])
                scroll = min(scroll, max(0, len(lines)-24))
                for row, line in enumerate(lines[scroll:scroll+24]):
                    text(line, 42, 165+row*19, 13)
                buttons = []
                button('Save report', (42, 668, 155, 42), 'save_report')
                button('Close', (212, 668, 100, 42), 'close_report')
            screen.blit(pg.transform.smoothscale(canvas, screen.get_size()), (0, 0))
            pg.display.flip()
            clock.tick(60)
            frames += 1
            if args.smoke_test and frames >= 10:
                running = False
        if args.screenshot:
            pg.image.save(canvas, args.screenshot)
    finally:
        close_device()
        pad.quit()
        pg.quit()


if __name__ == '__main__':
    main()
