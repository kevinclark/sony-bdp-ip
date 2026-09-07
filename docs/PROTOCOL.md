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

**Ruled out 2026-09-07 as a play-state source — the real working signal
is CERS `getStatus`, documented further down.** `GetTransportInfo` stayed
`NO_MEDIA_PRESENT` throughout an entire play → pause → stop cycle driven
by the player's own physical remote, confirmed twice, including a direct
query (bypassing HA/any caching) taken at the exact moment content was
confirmed actively playing on screen. IRCC's `X_GetStatus` was tried as a
fallback and also ruled out: its `CurrentCommandInfo` field decodes to
the same 13-byte structure as an `X_SendIRCC` command payload, and its
trailing command-code byte matched **the last IRCC command this session
had actually sent** (`0x16` = Eject, sent hours earlier) — it's an echo
of the last remote command processed, not a playback-state readout.

Working theory: `AVTransport` on this firmware is wired only for
DLNA-pushed ("Play To") content — a separate pipeline from local
disc/menu-driven playback — so it's a real UPnP MediaRenderer, just not
one that observes what the physical remote is doing. Kept below as
protocol documentation (the service is real and responds), but don't
build anything on it — use CERS `getStatus` instead, see further down.

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

## The actual working local-content signal: CERS `getStatus`

**Resolved 2026-09-07, after a second live disc test with a real
before/after comparison.** `getContentInformation` and `getStatus` (CERS,
port 50002, same auth as above) are **not** empty once a disc is actually
loaded — they were only empty in the very first test because there was no
disc in the drive. With a disc in:

```
GET http://<ip>:50002/getStatus
Authorization: Basic <base64>
X-CERS-DEVICE-ID: <client-id>
X-CERS-DEVICE-INFO: <client-id>
```

**At the player's own menu, with a disc loaded** (confirmed live):
```xml
<statusList>
  <status name="disc">
    <statusItem field="type" value="BD"/>
    <statusItem field="mediaType" value="BD-ROM"/>
    <statusItem field="mediaFormat" value="UHD"/>
  </status>
</statusList>
```

**Actively watching content — playing or paused, confirmed identical for
both** (this device does not distinguish play from pause anywhere; see
below):
```xml
<statusList>
  <status name="viewing">
    <statusItem field="class" value="video"/>
    <statusItem field="source" value="BD"/>
  </status>
  <status name="disc">
    <statusItem field="type" value="BD"/>
    <statusItem field="mediaType" value="BD-ROM"/>
    <statusItem field="mediaFormat" value="UHD"/>
  </status>
</statusList>
```

So: **presence of a `<status name="viewing">` entry is the real,
confirmed-working "content is actively being watched" signal** on this
device. `getContentInformation` returns the same `class`/`source`/
`mediaType`/`mediaFormat` fields regardless of viewing vs. menu (useful
for identifying the disc, not for playback state). `is_viewing_content()`
in `sony_bdp_ip/client.py` wraps this. This is what
`custom_components/sony_bdp`'s `media_player.ubp_x700` actually polls now
(not `AVTransport`, which is ruled out above).

**Confirmed NOT distinguishable, checked directly against the device
mid-pause**: playing vs. paused. `getStatus`/`getContentInformation` are
byte-for-byte identical in both states — the `viewing` entry is present
either way. Nothing found anywhere in this protocol (AVTransport, IRCC
status, or CERS status/content) separates the two. Practical conclusion:
**"is a movie actively being watched" is real and working; "is it
currently paused" is not achievable on this device with what's been
found.** The HA entity models this honestly — `playing` means "viewing,"
there is no `paused` state it will ever report.

`getHistoryList` — not yet tried.

## Open questions / next verification steps

- Confirm whether "Remote Start" is actually required for pairing, or was
  coincidental.
- Ports 50201/50202 are open but returned 404 for every path guessed
  (`/`, `/status`, `/dmr.xml`, `/description.xml`, `/webapi`,
  `/sony/system`, `/getPlayStatus`, `/getPlaybackStatus`,
  `/getPlayingStatus`) — no evidence either is actually used by this
  model; likely vestigial from the shared Bravia/BDP codebase (50202
  matches sonyapilib's old Bravia "app_port" default). Not pursued
  further without a better lead than guessing paths.
- Does pairing persist across player reboots/firmware updates, or does the
  `deviceId` need re-registering periodically?
- `getHistoryList` untried — name suggests playback history, unlikely to
  help with live state but unexplored.

## Two Home Assistant bugs found along the way (not protocol-specific)

Both cost real debugging time chasing what looked like protocol problems
but weren't. Neither is specific to this device — worth remembering for
any future custom_component work.

1. **A config-entry reload does not re-import a custom_component's `.py`
   files.** Editing `client.py`/`coordinator.py` on disk and reloading the
   config entry (`POST /api/config/config_entries/entry/{id}/reload`)
   reruns `async_setup_entry` using whatever module object Python already
   had cached in `sys.modules` from the first load — it does **not**
   re-read the file. This produced a very convincing false negative: the
   coordinator polled every 10s and logged "success: True" the whole
   time, entity state looked plausible (`idle`), and yet none of the new
   logic was actually running — it was still executing the old code.
   **Fix: a full `ha core restart` after editing a custom_component's
   code**, not just a config-entry reload. Config-entry reloads are fine
   for picking up config *data* changes (like a renamed title), just not
   code changes.
2. **Renaming a live entity's `entity_id` via
   `config/entity_registry/update` can silently orphan its
   `DataUpdateCoordinator`'s polling loop.** The entity kept showing its
   last-known value indefinitely (`last_reported` frozen) with zero
   errors logged, until the config entry was reloaded again afterward.
   Rule: always follow an entity_id rename with a config-entry reload
   before trusting that entity's live state.
