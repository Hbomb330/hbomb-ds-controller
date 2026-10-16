#!/usr/bin/env python3
"""
HBOMBRG // DUALSENSE BRIDGE
DualSense (USB or Bluetooth) -> virtual Xbox 360 / DualShock 4 pad + touchpad-as-mouse on Windows.

Needs the ViGEmBus driver for the virtual pad:
    https://github.com/nefarius/ViGEmBus/releases
Without it the app still runs touchpad mouse mode.
"""
import ctypes
import json
import os
import threading
import time
import zlib
import tkinter as tk
from tkinter import colorchooser

import hid

APP = "HBOMBRG // DUALSENSE BRIDGE"
SONY_VID = 0x054C
DS_PIDS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}
TP_W, TP_H = 1920, 1080

CFG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HBOMBRG", "dsbridge.json")
DEFAULTS = {
    "mode": "x360",       # "x360" or "ds4"
    "mouse": True,        # touchpad -> mouse
    "tap": True,          # tap to click
    "sens": 1.0,          # mouse speed
    "scroll": 1.0,        # two-finger scroll speed
    "deadzone": 0.08,     # radial stick deadzone (0..0.3)
    "rgb": [255, 0, 60],  # lightbar
}


# ============================================================ protocol
def parse_report(r):
    """Parse a full DualSense input report (USB 0x01 / BT 0x31). Returns dict or None."""
    if not r:
        return None
    if r[0] == 0x01 and len(r) >= 64:
        off = 1
    elif r[0] == 0x31 and len(r) >= 78:
        off = 2
    else:
        return None

    def touch(p):
        return {
            "down": not (r[p] & 0x80),
            "id": r[p] & 0x7F,
            "x": r[p + 1] | ((r[p + 2] & 0x0F) << 8),
            "y": (r[p + 2] >> 4) | (r[p + 3] << 4),
        }

    b0, b1, b2 = r[off + 7], r[off + 8], r[off + 9]
    status = r[off + 52]
    charging = (status >> 4) & 0x0F
    battery = 100 if charging == 2 else min((status & 0x0F) * 10 + 5, 100)
    return {
        "bt": r[0] == 0x31,
        "lx": r[off], "ly": r[off + 1], "rx": r[off + 2], "ry": r[off + 3],
        "l2": r[off + 4], "r2": r[off + 5],
        "b0": b0, "b1": b1, "b2": b2,
        "dpad": b0 & 0x0F,
        "ps": bool(b2 & 0x01), "tpad": bool(b2 & 0x02), "mute": bool(b2 & 0x04),
        "t1": touch(off + 32), "t2": touch(off + 36),
        "battery": battery, "charging": charging == 1,
    }


def build_output(bt, seq, small=0, large=0, rgb=(255, 0, 60), mute_led=0, player_leds=0x04, first=False):
    """Build an output report: rumble, lightbar, mute LED, player LEDs."""
    c = bytearray(47)
    c[0] = 0x01 | 0x02                 # compatible vibration + haptics select
    c[1] = 0x01 | 0x04 | 0x10          # mute LED, lightbar, player LEDs
    c[2] = small & 0xFF                # right (weak) motor
    c[3] = large & 0xFF                # left (strong) motor
    c[8] = mute_led
    if first:
        c[38] = 0x02                   # lightbar setup control
        c[41] = 0x02                   # release startup light animation
    c[43] = player_leds
    c[44], c[45], c[46] = (int(v) & 0xFF for v in rgb)
    if not bt:
        return bytes([0x02]) + bytes(c)
    buf = bytearray(78)
    buf[0] = 0x31
    buf[1] = (seq << 4) & 0xF0
    buf[2] = 0x10
    buf[3:50] = c
    crc = zlib.crc32(bytes([0xA2]) + bytes(buf[:74])) & 0xFFFFFFFF
    buf[74:78] = crc.to_bytes(4, "little")
    return bytes(buf)


# ============================================================ virtual pad
XB = dict(UP=0x1, DOWN=0x2, LEFT=0x4, RIGHT=0x8, START=0x10, BACK=0x20, LS=0x40, RS=0x80,
          LB=0x100, RB=0x200, GUIDE=0x400, A=0x1000, B=0x2000, X=0x4000, Y=0x8000)
HAT = {0: XB["UP"], 1: XB["UP"] | XB["RIGHT"], 2: XB["RIGHT"], 3: XB["DOWN"] | XB["RIGHT"],
       4: XB["DOWN"], 5: XB["DOWN"] | XB["LEFT"], 6: XB["LEFT"], 7: XB["UP"] | XB["LEFT"]}


def stick(vx, vy, dz):
    """Raw 0..255 axes -> (-32767..32767, Y up positive) with radial deadzone."""
    fx = (vx - 127.5) / 127.5
    fy = (127.5 - vy) / 127.5
    m = (fx * fx + fy * fy) ** 0.5
    if m <= dz or m == 0:
        return 0, 0
    k = min(1.0, (m - dz) / (1.0 - dz)) / m
    cl = lambda v: max(-32767, min(32767, int(v * k * 32767)))
    return cl(fx), cl(fy)


class VirtualPad:
    def __init__(self, mode, on_rumble):
        import vgamepad as vg  # Windows only, needs ViGEmBus
        self.mode = mode
        self.pad = vg.VX360Gamepad() if mode == "x360" else vg.VDS4Gamepad()

        def cb(client, target, large, small, *rest):
            on_rumble(large, small)

        self._cb = cb
        self.pad.register_notification(callback_function=cb)

    def send(self, s, dz, tpad_to_pad):
        rp = self.pad.report
        lx, ly = stick(s["lx"], s["ly"], dz)
        rx, ry = stick(s["rx"], s["ry"], dz)
        b0, b1 = s["b0"], s["b1"]
        if self.mode == "x360":
            w = HAT.get(s["dpad"], 0)
            for bit, name in ((0x10, "X"), (0x20, "A"), (0x40, "B"), (0x80, "Y")):
                if b0 & bit:
                    w |= XB[name]
            for bit, name in ((0x01, "LB"), (0x02, "RB"), (0x10, "BACK"),
                              (0x20, "START"), (0x40, "LS"), (0x80, "RS")):
                if b1 & bit:
                    w |= XB[name]
            if s["ps"]:
                w |= XB["GUIDE"]
            if s["tpad"] and tpad_to_pad:
                w |= XB["BACK"]
            rp.wButtons = w
            rp.bLeftTrigger, rp.bRightTrigger = s["l2"], s["r2"]
            rp.sThumbLX, rp.sThumbLY, rp.sThumbRX, rp.sThumbRY = lx, ly, rx, ry
        else:
            to8 = lambda x, y: (int(round(127.5 + x / 32767 * 127.5)), int(round(127.5 - y / 32767 * 127.5)))
            rp.wButtons = b0 | (b1 << 8)  # DS4 layout matches DualSense bit-for-bit
            rp.bSpecial = (1 if s["ps"] else 0) | (2 if (s["tpad"] and tpad_to_pad) else 0)
            rp.bTriggerL, rp.bTriggerR = s["l2"], s["r2"]
            rp.bThumbLX, rp.bThumbLY = to8(lx, ly)
            rp.bThumbRX, rp.bThumbRY = to8(rx, ry)
        self.pad.update()

    def close(self):
        try:
            self.pad.unregister_notification()
        except Exception:
            pass
        self.pad = None


# ============================================================ touchpad mouse
MOVE, LDOWN, LUP, RDOWN, RUP, WHEEL, HWHEEL = 0x1, 0x2, 0x4, 0x8, 0x10, 0x800, 0x1000


class Touchpad:
    def __init__(self):
        self.u = ctypes.windll.user32 if os.name == "nt" else None
        self.prev1 = self.prev2 = None
        self.ax = self.ay = self.sx = self.sy = 0.0
        self.btn = None
        self.t0 = 0
        self.travel = 0
        self.multi = False
        self.clicked = False

    def ev(self, flags, dx=0, dy=0, data=0):
        if self.u:
            self.u.mouse_event(flags, int(dx), int(dy), int(data), 0)

    def release(self):
        if self.btn:
            self.ev(LUP if self.btn == "L" else RUP)
            self.btn = None

    def update(self, s, cfg):
        t1, t2 = s["t1"], s["t2"]
        two = t1["down"] and t2["down"]
        now = time.monotonic()

        # physical click
        if s["tpad"] and not self.btn:
            right = two or (t1["down"] and t1["x"] > TP_W * 2 / 3)
            self.btn = "R" if right else "L"
            self.ev(RDOWN if right else LDOWN)
            self.clicked = True
        elif not s["tpad"] and self.btn:
            self.release()

        if two:
            self.multi = True
            if self.prev2:
                dy = ((t1["y"] + t2["y"]) - (self.prev2[1])) / 2
                dx = ((t1["x"] + t2["x"]) - (self.prev2[0])) / 2
                self.sy += dy * 3 * cfg["scroll"]
                self.sx -= dx * 3 * cfg["scroll"]
                if abs(self.sy) >= 1:
                    self.ev(WHEEL, data=int(self.sy)); self.sy -= int(self.sy)
                if abs(self.sx) >= 1:
                    self.ev(HWHEEL, data=int(self.sx)); self.sx -= int(self.sx)
            self.prev2 = (t1["x"] + t2["x"], t1["y"] + t2["y"])
            self.prev1 = None
            return
        self.prev2 = None

        if t1["down"]:
            if self.prev1 and self.prev1[2] == t1["id"]:
                dx, dy = t1["x"] - self.prev1[0], t1["y"] - self.prev1[1]
                self.travel += abs(dx) + abs(dy)
                speed = (dx * dx + dy * dy) ** 0.5
                gain = cfg["sens"] * 0.55 * (1 + min(speed / 25.0, 2.0))
                self.ax += dx * gain
                self.ay += dy * gain
                ix, iy = int(self.ax), int(self.ay)
                if ix or iy:
                    self.ev(MOVE, ix, iy)
                    self.ax -= ix; self.ay -= iy
            else:
                self.t0, self.travel, self.multi, self.clicked = now, 0, False, False
            self.prev1 = (t1["x"], t1["y"], t1["id"])
        else:
            if self.prev1 and cfg["tap"] and not self.clicked and not self.multi \
                    and now - self.t0 < 0.2 and self.travel < 40:
                self.ev(LDOWN); self.ev(LUP)
            self.prev1 = None
            self.ax = self.ay = 0.0


# ============================================================ bridge worker
class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dev = self.pad = None
        self.alive = True
        self.status = "Starting…"
        self.state = None
        self.name = ""
        self.tp = Touchpad()
        self.rumble = (0, 0)
        self.out_dirty = True
        self.first_out = True
        self.seq = 0
        self.last_out = 0
        self.last_rx = 0
        self.last_feat = 0
        self.prev_mute = False
        self.mode_dirty = False
        self.pad_error = ""

    # --- external hooks
    def on_rumble(self, large, small):
        self.rumble = (large, small)
        self.out_dirty = True

    def poke_output(self):
        self.out_dirty = True

    # --- connection
    def connect(self):
        info = next((d for d in hid.enumerate(SONY_VID, 0) if d["product_id"] in DS_PIDS), None)
        if not info:
            self.status = "Waiting for controller — pair over Bluetooth or plug in USB"
            return False
        try:
            dev = hid.device()
            dev.open_path(info["path"])
            try:
                dev.get_feature_report(0x05, 41)  # switches BT into full 0x31 reports
            except Exception:
                pass
        except Exception as e:
            self.status = f"Can't open controller: {e}"
            return False
        self.dev, self.name = dev, DS_PIDS[info["product_id"]]
        self.last_rx = time.monotonic()
        self.first_out = self.out_dirty = True
        self.make_pad()
        self.status = f"{self.name} connected"
        return True

    def make_pad(self):
        if self.pad:
            self.pad.close()
            self.pad = None
        try:
            self.pad = VirtualPad(self.cfg["mode"], self.on_rumble)
            self.pad_error = ""
        except Exception as e:
            self.pad_error = f"Virtual pad off — install ViGEmBus ({type(e).__name__})"

    def disconnect(self, why):
        self.tp.release()
        if self.pad:
            self.pad.close()
            self.pad = None
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev, self.state = None, None
        self.status = why

    # --- main loop
    def run(self):
        while self.alive:
            if not self.dev:
                if not self.connect():
                    time.sleep(1.0)
                    continue
            if self.mode_dirty:
                self.mode_dirty = False
                self.make_pad()
            try:
                r = self.dev.read(128, 50)
            except Exception:
                self.disconnect("Controller disconnected")
                continue
            now = time.monotonic()
            if r:
                self.last_rx = now
                s = parse_report(r)
                if s is None:
                    if r[0] == 0x01 and now - self.last_feat > 1:  # BT basic mode, ask for full
                        self.last_feat = now
                        try:
                            self.dev.get_feature_report(0x05, 41)
                        except Exception:
                            pass
                    continue
                self.handle(s)
            elif now - self.last_rx > 3:
                self.disconnect("Controller timed out — reconnecting")
                continue
            self.flush_output()
        self.disconnect("Stopped")

    def handle(self, s):
        cfg = self.cfg
        if s["mute"] and not self.prev_mute:  # MUTE toggles touchpad mouse
            cfg["mouse"] = not cfg["mouse"]
            if not cfg["mouse"]:
                self.tp.release()
            self.out_dirty = True
        self.prev_mute = s["mute"]

        if cfg["mouse"]:
            self.tp.update(s, cfg)
        if self.pad:
            try:
                self.pad.send(s, cfg["deadzone"], tpad_to_pad=not cfg["mouse"])
            except Exception as e:
                self.pad_error = f"Virtual pad error: {e}"
                self.pad = None
        self.state = s

    def flush_output(self):
        if not (self.out_dirty and self.state):
            return
        now = time.monotonic()
        if now - self.last_out < 0.012:
            return
        large, small = self.rumble
        pkt = build_output(self.state["bt"], self.seq, small, large, self.cfg["rgb"],
                           mute_led=1 if self.cfg["mouse"] else 0, first=self.first_out)
        try:
            self.dev.write(pkt)
            self.seq = (self.seq + 1) & 0x0F
            self.first_out = self.out_dirty = False
            self.last_out = now
        except Exception:
            pass


# ============================================================ UI
BG, PANEL, RED, CYAN, TXT, DIM = "#07070b", "#11111a", "#ff003c", "#00f0ff", "#e6e6f0", "#5d5d72"
FONT = ("Consolas", 10)
DPAD = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


def pressed(s):
    n = []
    if s["dpad"] < 8:
        n.append(DPAD[s["dpad"]])
    for bit, nm in ((0x10, "□"), (0x20, "✕"), (0x40, "○"), (0x80, "△")):
        if s["b0"] & bit: n.append(nm)
    for bit, nm in ((0x01, "L1"), (0x02, "R1"), (0x10, "CREATE"), (0x20, "OPTIONS"), (0x40, "L3"), (0x80, "R3")):
        if s["b1"] & bit: n.append(nm)
    if s["ps"]: n.append("PS")
    if s["tpad"]: n.append("PAD")
    if s["mute"]: n.append("MUTE")
    return "  ".join(n)


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


class App:
    def __init__(self):
        self.cfg = load_cfg()
        self.bridge = Bridge(self.cfg)
        self.root = root = tk.Tk()
        root.title("HBOMBRG DualSense Bridge")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.quit)

        tk.Label(root, text=APP, bg=BG, fg=RED, font=("Consolas", 14, "bold")).pack(padx=16, pady=(14, 2), anchor="w")
        self.status = tk.Label(root, text="", bg=BG, fg=CYAN, font=FONT, anchor="w", justify="left")
        self.status.pack(padx=16, fill="x")

        self.cv = tk.Canvas(root, width=480, height=230, bg=PANEL, highlightthickness=1, highlightbackground=RED)
        self.cv.pack(padx=16, pady=10)

        f = tk.Frame(root, bg=BG)
        f.pack(padx=16, fill="x")
        self.v_mode = tk.StringVar(value=self.cfg["mode"])
        tk.Label(f, text="OUTPUT", bg=BG, fg=DIM, font=FONT).grid(row=0, column=0, sticky="w")
        for i, (val, lbl) in enumerate((("x360", "Xbox 360"), ("ds4", "DualShock 4"))):
            tk.Radiobutton(f, text=lbl, value=val, variable=self.v_mode, command=self.set_mode, **self.chk()).grid(row=0, column=1 + i, sticky="w")

        self.v_mouse = tk.BooleanVar(value=self.cfg["mouse"])
        self.v_tap = tk.BooleanVar(value=self.cfg["tap"])
        tk.Label(f, text="TOUCHPAD", bg=BG, fg=DIM, font=FONT).grid(row=1, column=0, sticky="w")
        tk.Checkbutton(f, text="Mouse", variable=self.v_mouse, command=self.set_flags, **self.chk()).grid(row=1, column=1, sticky="w")
        tk.Checkbutton(f, text="Tap to click", variable=self.v_tap, command=self.set_flags, **self.chk()).grid(row=1, column=2, sticky="w")

        self.scale(f, 2, "MOUSE SPEED", "sens", 0.2, 3.0, 0.1)
        self.scale(f, 3, "SCROLL SPEED", "scroll", 0.2, 3.0, 0.1)
        self.scale(f, 4, "DEADZONE", "deadzone", 0.0, 0.3, 0.01)

        tk.Label(f, text="LIGHTBAR", bg=BG, fg=DIM, font=FONT).grid(row=5, column=0, sticky="w", pady=4)
        self.swatch = tk.Button(f, text="  pick color  ", command=self.pick, relief="flat", font=FONT, fg=BG, activeforeground=BG)
        self.swatch.grid(row=5, column=1, sticky="w")
        self.paint_swatch()

        self.err = tk.Label(root, text="", bg=BG, fg=RED, font=FONT, anchor="w")
        self.err.pack(padx=16, fill="x")
        tk.Label(root, text="MUTE = toggle touchpad mouse · 1 finger move · 2 finger scroll · click right third = right click",
                 bg=BG, fg=DIM, font=("Consolas", 8)).pack(padx=16, pady=(2, 12), anchor="w")

        self.thread = threading.Thread(target=self.bridge.run, daemon=True)
        self.thread.start()
        self.tick()

    def chk(self):
        return dict(bg=BG, fg=TXT, selectcolor=PANEL, activebackground=BG, activeforeground=CYAN, font=FONT, highlightthickness=0)

    def scale(self, f, row, label, key, lo, hi, res):
        tk.Label(f, text=label, bg=BG, fg=DIM, font=FONT).grid(row=row, column=0, sticky="w")
        sc = tk.Scale(f, from_=lo, to=hi, resolution=res, orient="horizontal", length=260, bg=BG, fg=TXT,
                      troughcolor=PANEL, highlightthickness=0, activebackground=RED, font=FONT, sliderrelief="flat",
                      command=lambda v, k=key: self.set_val(k, float(v)))
        sc.set(self.cfg[key])
        sc.grid(row=row, column=1, columnspan=2, sticky="w")

    def set_val(self, k, v):
        self.cfg[k] = v
        save_cfg(self.cfg)

    def set_mode(self):
        if self.cfg["mode"] != self.v_mode.get():
            self.cfg["mode"] = self.v_mode.get()
            self.bridge.mode_dirty = True
            save_cfg(self.cfg)

    def set_flags(self):
        self.cfg["mouse"], self.cfg["tap"] = self.v_mouse.get(), self.v_tap.get()
        if not self.cfg["mouse"]:
            self.bridge.tp.release()
        self.bridge.poke_output()
        save_cfg(self.cfg)

    def pick(self):
        c = colorchooser.askcolor(color="#%02x%02x%02x" % tuple(self.cfg["rgb"]), title="Lightbar")
        if c and c[0]:
            self.cfg["rgb"] = [int(x) for x in c[0]]
            self.paint_swatch()
            self.bridge.poke_output()
            save_cfg(self.cfg)

    def paint_swatch(self):
        hx = "#%02x%02x%02x" % tuple(self.cfg["rgb"])
        self.swatch.configure(bg=hx, activebackground=hx)

    def tick(self):
        b = self.bridge
        s = b.state
        line = b.status
        if s:
            link = "Bluetooth" if s["bt"] else "USB"
            mode = "XBOX 360" if self.cfg["mode"] == "x360" else "DS4"
            line = f"{b.name} · {link} · battery {s['battery']}%{' ⚡' if s['charging'] else ''} · {mode} · mouse {'ON' if self.cfg['mouse'] else 'OFF'}"
        self.status.configure(text=line)
        self.err.configure(text=b.pad_error)
        if self.v_mouse.get() != self.cfg["mouse"]:
            self.v_mouse.set(self.cfg["mouse"])
        self.draw(s)
        self.root.after(33, self.tick)

    def draw(self, s):
        cv = self.cv
        cv.delete("all")
        for cx in (70, 410):
            cv.create_oval(cx - 50, 60, cx + 50, 160, outline=DIM, width=2)
        cv.create_rectangle(160, 40, 320, 130, outline=CYAN, width=2)
        for x in (40, 380):
            cv.create_rectangle(x, 14, x + 60, 26, outline=DIM)
        cv.create_text(240, 25, text="TOUCHPAD", fill=DIM, font=("Consolas", 8))
        if not s:
            cv.create_text(240, 200, text="NO SIGNAL", fill=RED, font=("Consolas", 12, "bold"))
            return
        for cx, x, y, l3 in ((70, s["lx"], s["ly"], s["b1"] & 0x40), (410, s["rx"], s["ry"], s["b1"] & 0x80)):
            px, py = cx + (x - 128) / 128 * 44, 110 + (y - 128) / 128 * 44
            cv.create_oval(px - 9, py - 9, px + 9, py + 9, fill=RED if l3 else CYAN, outline="")
        cv.create_rectangle(40, 14, 40 + s["l2"] / 255 * 60, 26, fill=RED, outline="")
        cv.create_rectangle(380, 14, 380 + s["r2"] / 255 * 60, 26, fill=RED, outline="")
        if s["tpad"]:
            cv.create_rectangle(160, 40, 320, 130, fill="#2a0010", outline=RED, width=2)
        for t in (s["t1"], s["t2"]):
            if t["down"]:
                px, py = 160 + t["x"] / TP_W * 160, 40 + t["y"] / TP_H * 90
                cv.create_oval(px - 6, py - 6, px + 6, py + 6, fill=RED, outline=TXT)
        cv.create_text(240, 200, text=pressed(s) or "—", fill=TXT, font=("Consolas", 11, "bold"))

    def quit(self):
        self.bridge.alive = False
        self.thread.join(timeout=1.5)
        save_cfg(self.cfg)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
