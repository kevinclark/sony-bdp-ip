# sony-bdp-ip

IP control for Sony BDP-CE Blu-ray players (developed and tested against a
**Sony UBP-X700**, `BDP-2018`), plus (eventually) a Home Assistant
integration built on top of it.

Sony's IP control API for these players was never officially documented —
it's the same protocol the **Video & TV SideView** app used (that app
sunsets 2027-03-30), reverse-engineered here against a real device. Full
protocol notes: [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Status

Early / in progress. So far, confirmed live against a real UBP-X700:

- [x] Playback state (playing/paused/stopped/no-disc) — no pairing needed
- [x] Basic system info + WOL MAC — no pairing needed
- [x] Wake-on-LAN power-on (device confirms WOL support; not yet tested end-to-end from cold)
- [x] PIN pairing flow — confirmed live 2026-09-07
- [x] Remote control (play/pause/stop/power/eject/...) via IRCC — confirmed live, eject physically verified
- [ ] Home Assistant integration (`custom_components/sony_bdp`)

## Layout

- `sony_bdp_ip/` — the standalone protocol client, no HA dependency.
- `custom_components/sony_bdp/` — Home Assistant integration wrapping it
  (not started yet).
- `docs/PROTOCOL.md` — protocol reference.

## Quick usage

```python
from sony_bdp_ip import SonyBdpClient

client = SonyBdpClient(host="192.168.20.244", mac="88:c9:e8:61:66:c5")
print(client.get_transport_state())      # TransportState.NO_MEDIA
print(client.get_system_information())   # {"name": "BDPlayer", ...}
```

Pairing (one-time; needs the projector/receiver on so the PIN — shown as
on-screen text over HDMI — is visible):

```python
client.begin_pairing()          # player now displays a PIN
client.complete_pairing("5544")  # whatever PIN it showed
client.eject()                   # or .play() / .pause() / .stop() / .power()
```

`client_id` (constructor arg, defaults to `"home-assistant"`) plus the PIN
together act as the credential — keep both if you want to skip re-pairing
on restart; there's no separate token/cookie issued.
