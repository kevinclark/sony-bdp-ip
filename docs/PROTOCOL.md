# Sony UBP-X700 IP control protocol notes

Reverse-engineered/confirmed live against a real Sony **UBP-X700** (model
number `BDP-2018`, generation 2017, MAC `88:c9:e8:61:66:c5`) on 2026-09-07.
This is Sony's legacy "CERS" control scheme — the same one used by the
**Video & TV SideView** app (sunsetting 2027-03-30) for Blu-ray players,
Bravia TVs, and AV receivers of that era. Cross-referenced against a
Crestron forum thread (groups.io, inaccessible directly due to a bot-check
wall) and the [sonyapilib](https://github.com/gohlas/sonyapilib) Python
project, which implements the same API for Bravia devices.

## Ports

Confirmed open on the player when powered on:

| Port  | Purpose |
|-------|---------|
| 50001 | IRCC control (`/upnp/control/IRCC`) + device descriptor (`/Ircc.xml`) |
| 50002 | CERS registration + info actions (`/register`, `/getSystemInformation`, etc.) |
| 50201 | Open, unidentified (404 on `/`, same `Sony-BDP/2.0` server header) |
| 50202 | Open, unidentified (404 on `/`, same `Sony-BDP/2.0` server header) |
| 52323 | DLNA/UPnP MediaRenderer — `dmr.xml`, `AVTransport`, `RenderingControl` |

All confirmed via `nc`/`curl` from a host on the same VLAN. Nothing responds
at all (no ping, no ARP) while the player is fully powered off — it relies
entirely on Wake-on-LAN at the Ethernet frame level, which needs no IP
stack to be up. `dmr.xml` explicitly advertises
`<microsoft:magicPacketWakeSupported>1</microsoft:magicPacketWakeSupported>`,
and CERS `getSystemInformation` confirms `<function name="WOL"><functionItem
field="MAC" value="88-c9-e8-61-66-c5"/></function>`.

## Playback / transport state — reachable, but does NOT reflect local playback

**Update 2026-09-07, live disc test: this does not work for local disc
playback.** `GetTransportInfo` stayed `NO_MEDIA_PRESENT` throughout an
entire play → pause → stop cycle driven by the player's own physical
remote, confirmed twice, including a direct query (bypassing HA/any
caching) taken at the exact moment content was confirmed actively playing
on screen. IRCC's `X_GetStatus` was tried as a fallback and also ruled
out: its `CurrentCommandInfo` field decodes to the same 13-byte structure
as an `X_SendIRCC` command payload, and its trailing command-code byte
matched **the last IRCC command this session had actually sent** (`0x16`
= Eject, sent hours earlier) — it's an echo of the last remote command
processed, not a playback-state readout.

Working theory: `AVTransport` on this firmware is wired only for
DLNA-pushed ("Play To") content — a separate pipeline from local
disc/menu-driven playback — so it's a real UPnP MediaRenderer, just not
one that observes what the physical remote is doing. Below is kept as
protocol documentation (the service is real and responds), but **don't
build an HA play-state signal on it** — see the "Known gaps" note in the
main `ha` repo's `CLAUDE.md` for the automation that was built then
reverted based on this finding.

Standard UPnP `AVTransport` service, no auth needed at all:

```
POST http://<ip>:52323/upnp/control/AVTransport HTTP/1.1
Content-Type: text/xml; charset="utf-8"
SOAPACTION: "urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"

<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
    </u:GetTransportInfo>
  </s:Body>
</s:Envelope>
```

Response body contains `<CurrentTransportState>`, one of the standard UPnP
AVTransport values: `PLAYING`, `PAUSED_PLAYBACK`, `STOPPED`,
`NO_MEDIA_PRESENT`, `TRANSITIONING`. Initially assumed this would be the
long-missing play/pause/stop signal for the theater automation — **it
is not**, for local disc playback (see the update above).

IRCC also exposes an unauthenticated status query:

```
POST http://<ip>:50001/upnp/control/IRCC HTTP/1.1
Content-Type: text/xml; charset="utf-8"
SOAPACTION: "urn:schemas-sony-com:service:IRCC:1#X_GetStatus"

<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:X_GetStatus xmlns:u="urn:schemas-sony-com:service:IRCC:1">
      <CategoryCode>AAMAABxa</CategoryCode>
    </u:X_GetStatus>
  </s:Body>
</s:Envelope>
```

Returns `<CurrentStatus>` (integer, always seen as `0`) and
`<CurrentCommandInfo>` (base64). **Decoded 2026-09-07: `CurrentCommandInfo`
is an echo of the last `X_SendIRCC` command this session sent, not a
playback-state readout.** It decodes to the same byte layout as an IRCC
command payload — `CategoryCode bytes (6) + 00 00 00 <command-code-byte>`
— e.g. after sending Eject (`AAAAAwAAHFoAAAAWAw==`, command byte `0x16`),
`X_GetStatus` returned `AAMAABxaAAAAFg==` (also ending in `0x16`), even
though nothing had actually ejected/changed since. A response taken right
after pairing with no commands sent yet was all zero bytes. Ruled out as a
play-state source for this reason.

CERS `getSystemInformation` (plain `GET`, no auth) returns model/generation/
supported remote types/WOL MAC — useful for identification but not state.

## Control (play/pause/stop/power, remote buttons) — requires pairing

The player answers `401 Unauthorized` /
`WWW-Authenticate: Basic realm="Sony-BDP registration"` on the register
endpoint until paired. Confirmed live.

**One prerequisite found live**: the player's Setup → Network menu has a
"Remote Start" option, off by default, that (per Sony's docs) governs
whether app-based remote control/registration is allowed. We turned it on
before pairing worked — not confirmed as strictly required (registration
may well have worked with it off too, since basic queries never needed it),
but flip it on before attempting pairing to rule it out as a variable.

Registration action is discovered from `/Ircc.xml`'s
`X_CERS_ActionList_URL`, which points to `http://<ip>:50002/actionList`:

```xml
<action name="register" mode="3"
        url="http://<ip>:50002/register"/>
```

`mode="3"` = HTTP Basic-auth PIN challenge flow, **fully confirmed live
end-to-end 2026-09-07**:

1. `GET http://<ip>:50002/register?name=<client-name>&registrationType=initial&deviceId=<client-id>&wolSupport=true`
   with no `Authorization` header → `401`. The player then shows a PIN.
   **This unit has no front-panel display at all**, so the PIN can only
   show as on-screen text over HDMI — the projector/receiver need to be on
   and fed from the player to read it. (This is a one-time cost for
   pairing only; none of the day-to-day calls below need a display on.)
2. Re-issue the identical request with `Authorization: Basic base64(":" + pin)`
   (i.e. empty username) → `200 OK`, empty body. No cookie is set — unlike
   the newer v4/JSON-RPC Bravia flow, this is stateless Basic auth.
3. Every subsequent authenticated call must carry:
   `Authorization: Basic base64(":" + pin)`,
   `X-CERS-DEVICE-ID: <client-id>`, `X-CERS-DEVICE-INFO: <client-id>`
   — same `client-id` used at registration.

Once paired, remote-button-style control goes through IRCC — **confirmed
live**, verified physically via the tray eject command:

```
POST http://<ip>:50001/upnp/control/IRCC HTTP/1.1
Content-Type: text/xml; charset="utf-8"
SOAPACTION: "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"
Authorization: Basic <base64>
X-CERS-DEVICE-ID: <client-id>
X-CERS-DEVICE-INFO: <client-id>

<?xml version="1.0" encoding="utf-8"?>
<s:Envelope ...>
  <s:Body>
    <u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">
      <IRCCCode>{base64 IRCC code}</IRCCCode>
    </u:X_SendIRCC>
  </s:Body>
</s:Envelope>
```

The full command table was pulled live from `getRemoteCommandList` (port
50002, same auth headers as above) — see `sony_bdp_ip/client.py`'s
`IRCC_CODES` for the complete confirmed list (Play, Pause, Stop, Power,
Eject, transport/menu/number-pad buttons, Netflix, etc.).

Other CERS actions gated behind the same pairing:
- `getContentInformation` — returned an empty `<statusList/>`-style
  response with no disc loaded; not yet seen with a disc in to know its
  real shape.
- `getStatus` — same, empty `<statusList/>` when idle.
- `getHistoryList` — not yet tried.

## Open questions / next verification steps

- **The real open question now: is there ANY read-only signal on this
  device that reflects local disc playback state?** `AVTransport` and
  IRCC's `X_GetStatus` are both ruled out (see above). Untried:
  `getContentInformation`/`getStatus` (CERS, port 50002) — both returned
  structurally-valid-but-empty XML with no disc loaded; worth one more
  live check with a disc actually playing, though given the AVTransport
  result, low expectation these differ (same underlying local-playback
  blind spot seems likely, not confirmed). If nothing pans out, the
  honest conclusion is this device has no local-playback state exposed
  over IP at all, full stop — control-only.
- Confirm whether "Remote Start" is actually required for pairing, or was
  coincidental.
- Confirm ports 50201/50202 (open, unidentified purpose — 50202 matches
  sonyapilib's Bravia "app_port" default, may be vestigial on this device).
- Does pairing persist across player reboots/firmware updates, or does the
  `deviceId` need re-registering periodically?
