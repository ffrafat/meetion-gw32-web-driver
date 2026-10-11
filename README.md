# Meetion GW32 Web Driver for Mac, Windows & Linux

**Live site: https://ffrafat.github.io/meetion-gw32-web-driver/**

A free, open-source driver and configurator for the **Meetion GW32 (MT-GW32)** tri-mode gaming mouse.
Meetion only ships a Windows `.exe`. This version runs entirely in your browser over WebHID, so it works on
**macOS (Intel and Apple Silicon), Windows, Linux and ChromeOS** with nothing to install.

![Meetion GW32 driver and software for Mac, Windows and Linux](docs/assets/og-meetion-gw32.jpg)

## Features

- Remap all 9 buttons, including the side buttons and the thumb wheel, in two button modes
- Mouse actions, DPI controls, media keys, browser keys, ready-made shortcuts, or any recorded key combination
- 4 DPI levels (400–8000) with indicator colors
- 12 RGB lighting effects with speed, brightness, color and a sleep timer
- Polling rate of 125, 250, 500 or 1000 Hz
- Configure over the USB-C cable or the 2.4G receiver. Wireless writes are acknowledged by the mouse and retried like the official driver
- Live battery level when connected
- Settings are stored on the mouse, so they keep working in every mode, including Bluetooth
- Export and import settings as JSON

## How to use

1. Connect the GW32 with its USB-C cable, or plug in the 2.4G receiver and switch the mouse to 2.4G mode.
2. Open https://ffrafat.github.io/meetion-gw32-web-driver/ in **Chrome, Edge, Brave or Opera**. Safari and Firefox don't support WebHID.
3. Click **Connect**, change your settings, then click **Apply**.

On **Linux**, let your user access the mouse once:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1d57", ATTRS{idProduct}=="fa6[01]", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/70-meetion-gw32.rules
sudo udevadm control --reload-rules
```

## Repository layout

- `docs/`: the website, served by GitHub Pages
- `meetion_gw32.py`: the same protocol as a Python command-line tool (`pip install hidapi`)

To preview the site locally:

```bash
python3 -m http.server 8765 --directory docs
```

Then open http://localhost:8765 in Chrome. WebHID only works on HTTPS or localhost.

## Protocol notes

Reverse-engineered from the official Windows driver (2025-04-08). Settings are HID feature reports sent to the
USB interface whose top-level collection uses usage page `0x0B` (VID `1d57`, PID `fa61` over the cable, `fa60` for the 2.4G receiver). The
mouse doesn't report its settings back, so the full configuration is written every time.

| Report | Purpose | Layout |
|---|---|---|
| `0x0C` | session start/end | `0c 0a P ~P 02 fd` (P = active mode 1/2) |
| `0x04` | DPI (per mode) | 8 levels: enable mask, >4000 mask, value/39, value/38, current level, RGB per level, checksum |
| `0x05` | lighting (per mode) | effect<<4, sleep/speed nibbles, brightness, RGB, checksum |
| `0x06` | polling rate | `06 09 i v ~v`, v = 8/4/2/1 for 125/250/500/1000 Hz |
| `0x08` | buttons (per mode) | 18 slots × 3 bytes, then a 16-bit sum of bytes 3..56, big-endian |

Checksums are plain 16-bit sums starting at byte 3.

The mouse reports status through input report `0x03`: `code = b1 | b2<<8`, `value = b3 | b4<<8`.
`0x4010` is a heartbeat sent every 2 s while the mouse is linked (value high byte = battery 1–10, low byte 0 = charging),
`0x5010` acknowledges a write (value 0 = OK), and `0x1000` reports a DPI level change. Over the receiver, every
settings packet is resent up to 10 times until it is acknowledged.

## Credits

Created by **[Faisal F Rafat](https://github.com/ffrafat)**.

Meetion and GW32 are trademarks of their respective owner. This project is independent and not affiliated with
or endorsed by Meetion. Product images © Meetion.
