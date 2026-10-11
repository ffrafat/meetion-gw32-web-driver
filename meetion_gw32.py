#!/usr/bin/env python3
"""Configure a MEETION GW32 mouse from macOS (USB cable).

Protocol reverse-engineered from the official Windows driver
("MEETION GW32 Gaming Mouse Driver", Mouse.exe + hiddriver_1.dll, 2025-04-08).
The driver only ever *writes* HID feature reports to the mouse's vendor
collection (usage page 0x0B); it never reads the configuration back, so this
tool always writes a complete configuration taken from a JSON file.

Usage:
    python3 meetion_gw32.py list
    python3 meetion_gw32.py default-config > gw32.json
    python3 meetion_gw32.py apply gw32.json --dry-run
    python3 meetion_gw32.py apply gw32.json

Requires: pip install hidapi
"""
import argparse
import json
import sys
import time

VID, PID_WIRED = 0x1D57, 0xFA61

# ---------------------------------------------------------------------------
# Button actions: name -> 3 firmware bytes (from the driver's action table).
# ---------------------------------------------------------------------------
ACTIONS = {
    "off": (1, 0, 0),
    "left": (2, 0, 0),
    "right": (3, 0, 0),
    "middle": (4, 0, 0),
    "back": (5, 0, 0),
    "forward": (6, 0, 0),
    "double_click": (7, 0, 0),
    "fire": (8, 0, 0),
    "scroll_up": (9, 0, 0),
    "scroll_down": (10, 0, 0),
    "tilt_left": (11, 0, 0),
    "tilt_right": (12, 0, 0),
    "dpi_cycle": (13, 0, 0),
    "dpi_up": (14, 0, 0),
    "dpi_down": (15, 0, 0),
    "easy_aim": (16, 0, 3),
    "led_loop": (41, 0, 3),
    "media_player": (21, 0, 0),
    "prev_track": (22, 0, 0),
    "next_track": (23, 0, 0),
    "play_pause": (24, 0, 0),
    "media_stop": (25, 0, 0),
    "mute": (26, 0, 0),
    "volume_up": (27, 0, 0),
    "volume_down": (28, 0, 0),
    "calculator": (29, 0, 0),
    "email": (30, 0, 0),
    "browser_forward": (32, 0, 0),
    "browser_back": (33, 0, 0),
    "browser_stop": (34, 0, 0),
    "my_computer": (35, 0, 0),
    "browser_refresh": (36, 0, 0),
    "browser_home": (37, 0, 0),
    "browser_search": (38, 0, 0),
}
KEY_ACTION = 0x11  # followed by <modifier bitmask> <HID keyboard usage>

MODIFIERS = {"ctrl": 0x01, "control": 0x01, "shift": 0x02, "alt": 0x04, "opt": 0x04,
             "option": 0x04, "cmd": 0x08, "command": 0x08, "win": 0x08, "gui": 0x08}

# HID keyboard usage IDs (USB HID Usage Tables, page 0x07).
KEYS = {chr(c): 0x04 + i for i, c in enumerate(range(ord("a"), ord("z") + 1))}
KEYS.update({str(n): 0x1E + (n - 1) for n in range(1, 10)})
KEYS.update({"0": 0x27, "enter": 0x28, "return": 0x28, "esc": 0x29, "escape": 0x29,
             "backspace": 0x2A, "delete": 0x2A, "tab": 0x2B, "space": 0x2C, "-": 0x2D,
             "minus": 0x2D, "=": 0x2E, "equal": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31,
             ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
             "capslock": 0x39, "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
             "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "forwarddelete": 0x4C,
             "end": 0x4D, "pagedown": 0x4E, "right_arrow": 0x4F, "left_arrow": 0x50,
             "down_arrow": 0x51, "up_arrow": 0x52})
KEYS.update({f"f{n}": 0x3A + (n - 1) for n in range(1, 13)})

# Physical button (as numbered in the Windows driver) -> firmware slot (0..17).
BUTTON_SLOTS = {
    "1_left": 0, "2_right": 1, "3_middle": 2, "4_top": 3, "5_side_front": 6,
    "6_side_back": 7, "7_thumbwheel_press": 10, "8_thumbwheel_down": 15,
    "9_thumbwheel_up": 14,
}
# Slots the GW32 doesn't expose in the driver UI; values are the driver's GW32 defaults.
HIDDEN_SLOT_DEFAULTS = {16: "scroll_up", 17: "scroll_down"}

LIGHT_MODES = ["off", "static", "breathing", "neon", "color_breathing", "color_static",
               "mixed_breathing", "rainbow_wave", "lightning", "static_mixed_color",
               "marquee", "marquee_2"]

POLLING = {125: 8, 250: 4, 500: 2, 1000: 1}

DPI_COLORS_DEFAULT = ["#ff0000", "#ffff00", "#0000ff", "#00ff00",
                      "#00ffff", "#ff0000", "#ff4000", "#ffffff"]

DEFAULT_CONFIG = {
    "active_mode": 1,
    "modes": {
        "1": {"1_left": "left", "2_right": "right", "3_middle": "middle", "4_top": "dpi_cycle",
              "5_side_front": "forward", "6_side_back": "back", "7_thumbwheel_press": "mute",
              "8_thumbwheel_down": "volume_down", "9_thumbwheel_up": "volume_up"},
        "2": {"1_left": "left", "2_right": "right", "3_middle": "middle", "4_top": "dpi_cycle",
              "5_side_front": "forward", "6_side_back": "back", "7_thumbwheel_press": "mute",
              "8_thumbwheel_down": "volume_down", "9_thumbwheel_up": "volume_up"},
    },
    "dpi": {"levels": [1200, 2400, 3200, 6400], "current": 2, "colors": DPI_COLORS_DEFAULT[:4]},
    "lighting": {"mode": "rainbow_wave", "speed": 6, "brightness": 8, "color": "#0000ff",
                 "sleep_timer": 10},
    "polling_hz": 1000,
}


# ---------------------------------------------------------------------------
# Packet builders (byte layouts mirror Mouse.exe exactly, including lengths).
# ---------------------------------------------------------------------------
def checksum(buf, start, end):
    s = sum(buf[start:end]) & 0xFFFF
    return s >> 8, s & 0xFF


def pkt_session(active_mode):
    """Report 0x0C, sent before and after every apply."""
    p = active_mode
    return bytes([0x0C, 0x0A, p, ~p & 0xFF, 0x02, 0xFD]).ljust(10, b"\0")


def parse_action(spec):
    spec = spec.strip().lower()
    if spec in ACTIONS:
        return ACTIONS[spec]
    if spec.startswith("key:"):
        mods, key = 0, None
        for part in spec[4:].split("+"):
            part = part.strip()
            if part in MODIFIERS:
                mods |= MODIFIERS[part]
            elif part in KEYS:
                key = KEYS[part]
            else:
                raise ValueError(f"unknown key '{part}' in '{spec}'")
        return (KEY_ACTION, mods, key or 0)
    raise ValueError(f"unknown action '{spec}' (see ACTIONS, or use key:cmd+c)")


def pkt_buttons(mode_index, buttons):
    slots = [ACTIONS["off"]] * 18
    for slot, name in HIDDEN_SLOT_DEFAULTS.items():
        slots[slot] = ACTIONS[name]
    for button, action in buttons.items():
        if button not in BUTTON_SLOTS:
            raise ValueError(f"unknown button '{button}' (expected one of {list(BUTTON_SLOTS)})")
        slots[BUTTON_SLOTS[button]] = parse_action(action)
    buf = bytearray(59)
    buf[0:3] = (0x08, 0x3B, mode_index + 1)
    for i, triple in enumerate(slots):
        buf[3 + 3 * i: 6 + 3 * i] = bytes(triple)
    buf[57], buf[58] = checksum(buf, 3, 57)
    return bytes(buf)


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def pkt_dpi(mode_index, dpi):
    levels = list(dpi["levels"])
    if not 1 <= len(levels) <= 8:
        raise ValueError("dpi.levels needs 1..8 entries")
    for v in levels:
        if not 400 <= v <= 8000 or v % 40:
            raise ValueError(f"DPI {v} must be 400..8000 in steps of 40")
    colors = list(dpi.get("colors", [])) + DPI_COLORS_DEFAULT[len(dpi.get("colors", [])):]
    current = dpi["current"]
    if not 1 <= current <= len(levels):
        raise ValueError("dpi.current must point at one of the levels (1-based)")

    enabled = hi = 0
    xs, ys = [0] * 8, [0] * 8
    for i in range(8):
        v = levels[i] if i < len(levels) else 0
        if i < len(levels):
            enabled |= 1 << i
        if v > 4000:
            hi |= 1 << i
            v *= 0.5
        xs[i] = int(v / 39 + 0.5)
        ys[i] = int(v / 38 + 0.5)

    buf = bytearray(56)
    buf[0:8] = (0x04, 0x38, mode_index + 1, 8, 8, enabled, hi, hi)
    buf[8:16] = bytes(xs)
    buf[16:24] = bytes(ys)
    buf[24] = current
    for i in range(8):
        buf[25 + 3 * i: 28 + 3 * i] = bytes(rgb(colors[i]))
    buf[49] = 2
    buf[50], buf[51] = checksum(buf, 3, 50)
    return bytes(buf)


def pkt_lighting(mode_index, light):
    mode = LIGHT_MODES.index(light["mode"])
    speed = light.get("speed", 6)            # driver slider range 4..8
    brightness = light.get("brightness", 8)  # 1..8, only used by static modes
    sleep = light.get("sleep_timer", 10)
    if not 4 <= speed <= 8 or not 1 <= brightness <= 8:
        raise ValueError("lighting.speed must be 4..8 and brightness 1..8")
    r, g, b = rgb(light.get("color", "#0000ff"))
    buf = bytearray(15)
    buf[0:3] = (0x05, 0x0F, mode_index + 1)
    buf[3] = (mode << 4) & 0xFF
    buf[4] = (sleep & 0xF0) | (9 - speed)
    buf[5] = ((sleep << 4) & 0xFF) | (brightness if mode in (1, 9) else 8)
    buf[6:9] = (r, g, b)
    buf[9] = 0
    buf[10] = 1
    buf[11], buf[12] = checksum(buf, 3, 11)
    return bytes(buf)


def pkt_polling(hz):
    v = POLLING[hz]
    return [bytes([0x06, 0x09, i, v, ~v & 0xFF]).ljust(9, b"\0") for i in (1, 2)]


def build_packets(cfg):
    active = int(cfg.get("active_mode", 1))
    pkts = [("session start", pkt_session(active))]
    for m in (0, 1):
        pkts.append((f"mode {m + 1} dpi", pkt_dpi(m, cfg["dpi"])))
        pkts.append((f"mode {m + 1} lighting", pkt_lighting(m, cfg["lighting"])))
        for p in pkt_polling(int(cfg["polling_hz"])):
            pkts.append((f"mode {m + 1} polling", p))
    for m in (0, 1):
        pkts.append((f"mode {m + 1} buttons", pkt_buttons(m, cfg["modes"][str(m + 1)])))
    pkts.append(("session end", pkt_session(active)))
    return pkts


# ---------------------------------------------------------------------------
# Device I/O
# ---------------------------------------------------------------------------
def find_device(pid):
    import hid
    for d in hid.enumerate(VID, pid):
        # The vendor feature reports live on the interface whose top-level
        # collection is System Control (macOS) / usage page 0x0B (Windows).
        if (d["usage_page"], d["usage"]) in ((0x01, 0x80), (0x0B, 0x00)):
            return d
    return None


def cmd_list(_args):
    import hid
    for d in hid.enumerate(VID, 0):
        print(f"{d['vendor_id']:04x}:{d['product_id']:04x} usage {d['usage_page']:#06x}/{d['usage']:#04x} "
              f"{d['product_string']!r} {d['path']!r}")


def cmd_default_config(_args):
    print(json.dumps(DEFAULT_CONFIG, indent=2))


def cmd_apply(args):
    with open(args.config) as f:
        cfg = json.load(f)
    pkts = build_packets(cfg)
    if args.dry_run:
        for label, p in pkts:
            print(f"{label:22s} {p.hex(' ')}")
        return
    import hid
    info = find_device(args.pid)
    if not info:
        sys.exit("GW32 not found. Connect it with the USB cable (or pass --pid for the dongle).")
    dev = hid.device()
    dev.open_path(info["path"])
    try:
        for label, p in pkts:
            n = dev.send_feature_report(p)
            print(f"{label:22s} sent {n} bytes")
            time.sleep(0.2)
    finally:
        dev.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list connected MEETION HID interfaces").set_defaults(fn=cmd_list)
    sub.add_parser("default-config", help="print the driver's GW32 defaults as JSON").set_defaults(fn=cmd_default_config)
    p = sub.add_parser("apply", help="write a JSON config to the mouse")
    p.add_argument("config")
    p.add_argument("--dry-run", action="store_true", help="print packets instead of sending")
    p.add_argument("--pid", type=lambda s: int(s, 0), default=PID_WIRED)
    p.set_defaults(fn=cmd_apply)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
