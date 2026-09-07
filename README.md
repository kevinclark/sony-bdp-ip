# sony-bdp-ip

IP control for Sony BDP-CE Blu-ray players (developed and tested against a
**Sony UBP-X700**, `BDP-2018`), plus (eventually) a Home Assistant
integration built on top of it.

Sony's IP control API for these players was never officially documented —
it's the same protocol the **Video & TV SideView** app used (that app
sunsets 2027-03-30), reverse-engineered here against a real device. Full
protocol notes: [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Status

Confirmed live against a real UBP-X700, 2026-09-07:

- [x] Basic system info + WOL MAC — no pairing needed
- [x] Wake-on-LAN power-on (device confirms WOL support; not yet tested end-to-end from cold)
- [x] PIN pairing flow
- [x] Remote control (play/pause/stop/power/eject/...) via IRCC — eject physically verified
- [x] Home Assistant integration (`custom_components/sony_bdp`) — deployed
  and live on a real HA instance, config-flow pairing walked through
  end-to-end via the actual UI
- [x] **"Actively watching content" signal — found, working, wired into
  the theater automation.** Not `AVTransport` (ruled out — see
  PROTOCOL.md, it only tracks DLNA-pushed content, not local disc
  playback) and not IRCC's `X_GetStatus` (ruled out — it just echoes the
  last IRCC command sent). The real signal is CERS `getStatus`: a
  `"viewing"` entry appears while content is on screen and disappears
  back at a menu, confirmed with live before/after comparisons.
  `media_player.ubp_x700` polls this and reports `playing`/`idle`
  accordingly; the theater automation now reacts to real Blu-ray state
  the same way it already did for Apple TV.
- [x] ~~Play vs. paused~~ **Confirmed not distinguishable**, checked
  directly against the device mid-pause: `getStatus` is byte-for-byte
  identical whether playing or paused. Nothing tried anywhere in this
  protocol separates the two. `media_player.ubp_x700` will only ever
  report `playing` or `idle`, never `paused` — that's accurate, not a
  bug to keep chasing.

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the full writeup, including
two real bugs found along the way that aren't specific to this device:
Home Assistant doesn't re-import a custom_component's `.py` files on a
config-entry reload (a full `ha core restart` is required after editing
code), and renaming a live entity's `entity_id` can silently orphan its
polling coordinator.

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
