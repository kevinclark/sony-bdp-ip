<!-- markdownlint-disable MD041 -->
# Sony BDP-CE Blu-ray Player for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

IP control for Sony's **BDP-CE** family of Blu-ray players — developed and
tested against a **UBP-X700** — plus a Home Assistant integration built on
top of it. Sony never officially documented this API; it's the same
protocol the **Video & TV SideView** app used before its sunset
(2027-03-30), reverse-engineered here against a real device and confirmed
live at every step. Full protocol writeup, including every dead end that
was ruled out along the way: [docs/PROTOCOL.md](docs/PROTOCOL.md).

## What you get

- A `media_player` entity: on/off, play/pause/stop/eject, and whether
  content is actively being watched — all over the network, no IR blaster.
- Wake-on-LAN power-on from full standby.
- Disc info (type/format) exposed as entity attributes when a disc is loaded.
- A config flow: add the integration, enter the host, pair with the PIN the
  player displays. No YAML required.

## Limitations (read this before filing an issue about it)

- **This device cannot distinguish playing from paused, and neither can
  this integration.** Checked directly against the device mid-pause —
  every status endpoint available returns identical results whether
  playing or paused. The entity's `playing` state means "content is on
  screen," full stop. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the
  four independent things that were tried and ruled out.
- Pairing needs a display connected and on, at least the first time — the
  PIN shows as on-screen text over HDMI (this unit has no front-panel
  display to fall back on).
- Only tested against a UBP-X700. Other BDP-CE-era Sony Blu-ray players
  (and possibly some AV receivers/TVs of the same generation, which shared
  this control scheme) may work but haven't been verified.

## Installation

### HACS (recommended)

1. HACS → the "⋮" menu → **Custom repositories** → add this repository's
   URL with category **Integration**.
2. Search for **"Sony BDP-CE Blu-ray Player"** in HACS and install it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/sony_bdp` into your `config/custom_components/`
directory and restart Home Assistant.

## Setup

**Settings → Devices & Services → Add Integration → "Sony BDP-CE Blu-ray
Player."** You'll need:

- The player's IP address (a static/reserved DHCP lease is strongly
  recommended — this integration doesn't do discovery).
- Its MAC address, if you want power-on via Wake-on-LAN (check the
  player's network settings menu, or your router's client list).

The player will then show a PIN as on-screen text — make sure a display is
on and fed from the player before you submit the form. Enter that PIN on
the next screen to finish pairing.

## Standalone Python library

`sony_bdp_ip` is the protocol client with no Home Assistant dependency, for
scripting or other integrations:

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

`custom_components/sony_bdp` vendors its own copy of this client (see that
file's docstring) rather than depending on it as a published package, since
`sony_bdp_ip` isn't on PyPI (yet).

## Contributing

Issues and PRs welcome — especially reports from other BDP-CE-family
devices (older/newer UBP/BDP models, AV receivers or TVs from the same
generation), and anyone who finds a real play/pause signal this project
missed. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full "here's
everything already tried" list before chasing that particular white
whale.

## License

[MIT](LICENSE)
