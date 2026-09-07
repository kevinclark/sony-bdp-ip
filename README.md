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

- [x] Basic system info + WOL MAC — no pairing needed
- [x] Wake-on-LAN power-on (device confirms WOL support; not yet tested end-to-end from cold)
- [x] PIN pairing flow — confirmed live 2026-09-07
- [x] Remote control (play/pause/stop/power/eject/...) via IRCC — confirmed live, eject physically verified
- [x] Home Assistant integration (`custom_components/sony_bdp`) — deployed
  and live on a real HA instance 2026-09-07: config-flow pairing walked
  through end-to-end via the actual UI.
- [x] ~~Playback state~~ **Ruled out 2026-09-07**: `AVTransport`'s
  `GetTransportInfo` does **not** reflect local disc playback on this
  device — confirmed with a live disc test (stayed `NO_MEDIA_PRESENT`
  throughout an actual play/pause/stop cycle, checked directly at the
  moment playback was confirmed happening). IRCC's `X_GetStatus` was
  tried as a fallback and also ruled out (it just echoes the last IRCC
  command sent). See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full
  writeup. **The original motivation for this whole project — telling
  the theater automation when the player is actually playing — is not
  achievable with what's been found so far.** The HA integration and
  automation change built on the (wrong) assumption that it was were
  reverted the same day; this repo's `media_player.ubp_x700` entity is
  control-only for now.
- [ ] Find *any* read-only local-playback signal on this device (see
  "Open questions" in PROTOCOL.md) — otherwise this device is genuinely
  control-only over IP, and that's a real, final answer, not a gap to
  keep chasing indefinitely.

## Layout

- `sony_bdp_ip/` — the standalone protocol client, no HA dependency.
- `custom_components/sony_bdp/` — Home Assistant integration wrapping it.
  Vendors its own copy of the client (see that file's docstring) rather
  than depending on `sony_bdp_ip` as a pip package, since the latter isn't
  published anywhere yet.
- `docs/PROTOCOL.md` — protocol reference.

## Quick usage

```python
from sony_bdp_ip import SonyBdpClient

client = SonyBdpClient(host="192.168.20.244", mac="88:c9:e8:61:66:c5")
print(client.get_transport_state())      # TransportState.NO_MEDIA — doesn't
                                          # track local disc playback, see Status
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
