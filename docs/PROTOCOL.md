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

## Playback / transport state — no pairing required

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
`NO_MEDIA_PRESENT`, `TRANSITIONING`. Verified live (returned
`NO_MEDIA_PRESENT` with no disc loaded). **This is the play/pause/stop
signal that was previously missing** for the theater automation — see the
main HA repo's `CLAUDE.md` ("no play-state signal exists for bluray").

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

Returns `<CurrentStatus>` (integer code, meaning not yet decoded) and
`<CurrentCommandInfo>` (base64, not yet decoded).

CERS `getSystemInformation` (plain `GET`, no auth) returns model/generation/
supported remote types/WOL MAC — useful for identification but not state.

## Control (play/pause/stop/power, remote buttons) — requires pairing

The player answers `401 Unauthorized` /
`WWW-Authenticate: Basic realm="Sony-BDP registration"` on the register
endpoint until paired. Confirmed live.

Registration action is discovered from `/Ircc.xml`'s
`X_CERS_ActionList_URL`, which points to `http://<ip>:50002/actionList`:

```xml
<action name="register" mode="3"
        url="http://<ip>:50002/register"/>
```

`mode="3"` = HTTP Basic-auth PIN challenge flow:

1. `GET http://<ip>:50002/register?name=<client-name>&registrationType=initial&deviceId=<client-id>&wolSupport=true`
   with no `Authorization` header. Confirmed: returns `401` and the player
   should display a PIN (location TBD — front panel vs. TV/projector output,
   not yet confirmed for this unit).
2. Re-issue the same request with `Authorization: Basic base64(":" + pin)`.
3. On success, subsequent requests must carry these headers on every call:
   `X-CERS-DEVICE-ID: <client-id>`, `X-CERS-DEVICE-INFO: <client-id>`.
   (Not cookie-based, unlike the newer v4/JSON-RPC Bravia flow.)

Once paired, remote-button-style control goes through IRCC:

```
POST http://<ip>:50001/upnp/control/IRCC HTTP/1.1
Content-Type: text/xml; charset="utf-8"
SOAPACTION: "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"
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

The actual IRCC code table for play/pause/stop/power has not yet been
pulled from this unit — CERS's `getRemoteCommandList` (port 50002) should
return it post-pairing; it returned empty when tried unauthenticated.

Other CERS actions gated behind the same pairing (all returned empty
unauthenticated): `getStatus`, `getContentInformation` (likely current
disc/title info), `getHistoryList`.

## Open questions / next verification steps

- Where does the pairing PIN actually display on this unit (front panel vs.
  HDMI OSD)? Determines whether pairing needs the projector/receiver on.
- Decode `getRemoteCommandList` once paired to get real IRCC codes for
  play/pause/stop/power.
- Decode `X_GetStatus`'s `CurrentStatus`/`CurrentCommandInfo` values.
- Confirm ports 50201/50202 (open, unidentified purpose).
