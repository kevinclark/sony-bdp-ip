<!-- markdownlint-disable MD041 -->
# sony-bdp-ip

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Python client for the undocumented IP control protocol used by Sony's
**BDP-CE** family of Blu-ray players — developed and tested against a
**UBP-X700**. No official Sony documentation exists for this; it's the
same protocol the **Video & TV SideView** app used before its sunset
(2027-03-30), reverse-engineered against a real device and confirmed live
at every step. Full protocol write-up, including every dead end that was
ruled out along the way: [docs/PROTOCOL.md](docs/PROTOCOL.md).

Looking for the **Home Assistant integration**? It lives in a separate
repo: [**home-assistant-sony-bdp**](https://github.com/kevinclark/home-assistant-sony-bdp).

## What it does

- Wake-on-LAN power-on, and reading basic system info — no pairing needed.
- Remote-button-style control (play/pause/stop/eject/power/...) via a
  one-time PIN pairing.
- "Is content actively being watched right now" — the actual usable local
  state signal on this device, found the hard way (see Limitations).

## Limitations

- **This device cannot distinguish playing from paused.** Checked directly
  against the device mid-pause — every status endpoint available returns
  identical results whether playing or paused. `is_viewing_content()`
  means "content is on screen," full stop. See
  [docs/PROTOCOL.md](docs/PROTOCOL.md) for the four independent things
  that were tried and ruled out.
- **No disc/movie title or artwork is available either** — only physical
  format (BD/BD-ROM/UHD). See docs/PROTOCOL.md for why.
- Pairing needs a display connected and on, at least the first time — the
  PIN shows as on-screen text over HDMI (this unit has no front-panel
  display to fall back on).
- Only tested against a UBP-X700. Other BDP-CE-era Sony Blu-ray players
  (and possibly some AV receivers/TVs of the same generation, which shared
  this control scheme) may work but haven't been verified.

## Installation

Not yet published to PyPI. Install directly from GitHub:

```bash
pip install git+https://github.com/kevinclark/sony-bdp-ip.git
```

## Usage

```python
from sony_bdp_ip import SonyBdpClient

client = SonyBdpClient(host="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")

client.get_system_information()   # {"name": "BDPlayer", "mac": "...", ...}

client.begin_pairing()            # player now displays a PIN
client.complete_pairing("1234")   # whatever PIN it showed

client.play()
client.pause()
client.is_viewing_content()       # True while content is on screen
client.wake_on_lan()
```

See [sony_bdp_ip/client.py](sony_bdp_ip/client.py) for the full API —
every method is documented inline with what it needs (pairing or not) and
what was verified live against a real device.

## Contributing

Issues and PRs welcome — especially reports from other BDP-CE-family
devices (older/newer UBP/BDP models, AV receivers or TVs from the same
generation), and anyone who finds a real play/pause signal this project
missed. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full "here's
everything already tried" list before chasing that particular white
whale.

## License

[MIT](LICENSE)
