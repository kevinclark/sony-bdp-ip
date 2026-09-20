"""IP control client for Sony BDP-CE Blu-ray players (e.g. UBP-X700).

Protocol details are documented in docs/PROTOCOL.md. In short: the local
playback signal is CERS `getStatus` (see get_status()/is_viewing_content()),
not the standard UPnP AVTransport service exposed on the DMR port — that
one is real and unauthenticated but appears wired only for DLNA-pushed
content, not local disc/menu playback (see get_transport_state()). Actual
remote control (play/pause/power/etc.) goes through a Sony-specific IRCC
service that requires a one-time PIN pairing.
"""

from __future__ import annotations

import base64
import socket
from enum import Enum
from xml.etree import ElementTree

import requests

DEFAULT_IRCC_PORT = 50001
DEFAULT_CERS_PORT = 50002
DEFAULT_DMR_PORT = 52323
TIMEOUT = 5

# Confirmed live against a UBP-X700 (BDP-2018) via getRemoteCommandList
# after pairing. Same firmware family should match; call
# get_remote_commands() to fetch the device's own table instead of trusting
# this if you're on different hardware.
IRCC_CODES = {
    "Confirm": "AAAAAwAAHFoAAAA9Aw==",
    "Up": "AAAAAwAAHFoAAAA5Aw==",
    "Down": "AAAAAwAAHFoAAAA6Aw==",
    "Right": "AAAAAwAAHFoAAAA8Aw==",
    "Left": "AAAAAwAAHFoAAAA7Aw==",
    "Home": "AAAAAwAAHFoAAABCAw==",
    "Options": "AAAAAwAAHFoAAAA/Aw==",
    "Return": "AAAAAwAAHFoAAABDAw==",
    "Num1": "AAAAAwAAHFoAAAAAAw==",
    "Num2": "AAAAAwAAHFoAAAABAw==",
    "Num3": "AAAAAwAAHFoAAAACAw==",
    "Num4": "AAAAAwAAHFoAAAADAw==",
    "Num5": "AAAAAwAAHFoAAAAEAw==",
    "Num6": "AAAAAwAAHFoAAAAFAw==",
    "Num7": "AAAAAwAAHFoAAAAGAw==",
    "Num8": "AAAAAwAAHFoAAAAHAw==",
    "Num9": "AAAAAwAAHFoAAAAIAw==",
    "Num0": "AAAAAwAAHFoAAAAJAw==",
    "Power": "AAAAAwAAHFoAAAAVAw==",
    "Display": "AAAAAwAAHFoAAABBAw==",
    "Audio": "AAAAAwAAHFoAAABkAw==",
    "SubTitle": "AAAAAwAAHFoAAABjAw==",
    "Favorites": "AAAAAwAAHFoAAABeAw==",
    "Yellow": "AAAAAwAAHFoAAABpAw==",
    "Blue": "AAAAAwAAHFoAAABmAw==",
    "Red": "AAAAAwAAHFoAAABnAw==",
    "Green": "AAAAAwAAHFoAAABoAw==",
    "Play": "AAAAAwAAHFoAAAAaAw==",
    "Stop": "AAAAAwAAHFoAAAAYAw==",
    "Pause": "AAAAAwAAHFoAAAAZAw==",
    "Rewind": "AAAAAwAAHFoAAAAbAw==",
    "Forward": "AAAAAwAAHFoAAAAcAw==",
    "Prev": "AAAAAwAAHFoAAABXAw==",
    "Next": "AAAAAwAAHFoAAABWAw==",
    "Replay": "AAAAAwAAHFoAAAB2Aw==",
    "Advance": "AAAAAwAAHFoAAAB1Aw==",
    "Angle": "AAAAAwAAHFoAAABlAw==",
    "TopMenu": "AAAAAwAAHFoAAAAsAw==",
    "PopUpMenu": "AAAAAwAAHFoAAAApAw==",
    "Eject": "AAAAAwAAHFoAAAAWAw==",
    "Karaoke": "AAAAAwAAHFoAAABKAw==",
    "Netflix": "AAAAAwAAHFoAAABLAw==",
    "Mode3D": "AAAAAwAAHFoAAABNAw==",
}

_SOAP_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>{body}</s:Body>
</s:Envelope>"""

_NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "avt": "urn:schemas-upnp-org:service:AVTransport:1",
    "ircc": "urn:schemas-sony-com:service:IRCC:1",
    "upnp": "urn:schemas-upnp-org:device-1-0",
}


class TransportState(str, Enum):
    """Values of AVTransport's CurrentTransportState."""

    PLAYING = "PLAYING"
    PAUSED = "PAUSED_PLAYBACK"
    STOPPED = "STOPPED"
    NO_MEDIA = "NO_MEDIA_PRESENT"
    TRANSITIONING = "TRANSITIONING"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_str(cls, value: str) -> "TransportState":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


class PairingRequired(Exception):
    """Raised when an action needs pairing that hasn't happened yet."""


class SonyBdpClient:
    """Talks to a single Sony BDP-CE device over IP."""

    def __init__(
        self,
        host: str,
        client_id: str = "sony-bdp-ip",
        nickname: str = "sony-bdp-ip",
        ircc_port: int = DEFAULT_IRCC_PORT,
        cers_port: int = DEFAULT_CERS_PORT,
        dmr_port: int = DEFAULT_DMR_PORT,
        mac: str | None = None,
    ) -> None:
        self.host = host
        self.client_id = client_id
        self.nickname = nickname
        self.ircc_port = ircc_port
        self.cers_port = cers_port
        self.dmr_port = dmr_port
        self.mac = mac
        self.pin: str | None = None
        self._commands: dict[str, str] | None = None

    @property
    def is_paired(self) -> bool:
        return self.pin is not None

    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "X-CERS-DEVICE-ID": self.client_id,
            "X-CERS-DEVICE-INFO": self.client_id,
        }
        if self.pin is not None:
            token = base64.b64encode(f":{self.pin}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        return headers

    def _soap_request(self, url: str, action: str, body: str) -> ElementTree.Element:
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{action}"',
            **self._auth_headers(),
        }
        response = requests.post(
            url,
            headers=headers,
            data=_SOAP_ENVELOPE.format(body=body),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return ElementTree.fromstring(response.content)

    def get_transport_state(self) -> TransportState:
        """Query AVTransport's play/pause/stop state. Needs no pairing.

        Does NOT reflect local disc/menu playback — this stayed
        NO_MEDIA_PRESENT throughout a real play/pause/stop cycle in
        testing. Appears wired only for DLNA-pushed ("Play To") content.
        For local playback, use is_viewing_content()/get_status() instead.
        See docs/PROTOCOL.md for the full investigation.
        """
        url = f"http://{self.host}:{self.dmr_port}/upnp/control/AVTransport"
        action = "urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"
        body = (
            '<u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            "<InstanceID>0</InstanceID></u:GetTransportInfo>"
        )
        root = self._soap_request(url, action, body)
        state_el = root.find(".//avt:CurrentTransportState", _NS)
        if state_el is None or state_el.text is None:
            return TransportState.UNKNOWN
        return TransportState.from_str(state_el.text)

    def get_device_info(self) -> dict[str, str | None]:
        """Friendly name/model from the player's own UPnP descriptor (dmr.xml).

        Needs no pairing. Useful for a sensible display name — CERS's
        getSystemInformation returns a generic internal name ("BDPlayer"),
        not the model people would recognize (e.g. "UBP-X700").
        """
        url = f"http://{self.host}:{self.dmr_port}/dmr.xml"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)

        def text(tag: str) -> str | None:
            el = root.find(f".//upnp:{tag}", _NS)
            return el.text if el is not None and el.text else None

        return {
            "friendly_name": text("friendlyName"),
            "model_name": text("modelName"),
            "model_number": text("modelNumber"),
        }

    def get_system_information(self) -> dict[str, str | None]:
        """Model/generation/WOL-MAC info. Needs no pairing."""
        url = f"http://{self.host}:{self.cers_port}/getSystemInformation"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)

        mac = None
        for item in root.iter("functionItem"):
            if item.get("field") == "MAC":
                mac = item.get("value")

        def text(tag: str) -> str | None:
            el = root.find(tag)
            return el.text if el is not None else None

        return {
            "name": text("name"),
            "generation": text("generation"),
            "mac": mac,
        }

    def begin_pairing(self) -> bool:
        """Kick off pairing. Returns True once the device is waiting for a PIN.

        The PIN shows up as on-screen text over HDMI (confirmed: the
        UBP-X700 has no front-panel display), so a display needs to be on
        and fed from the player to read it. Pass the PIN to
        complete_pairing().
        """
        url = (
            f"http://{self.host}:{self.cers_port}/register"
            f"?name={self.nickname}&registrationType=initial"
            f"&deviceId={self.client_id}&wolSupport=true"
        )
        response = requests.get(url, headers=self._auth_headers(), timeout=TIMEOUT)
        return response.status_code == 401

    def complete_pairing(self, pin: str) -> bool:
        """Finish pairing with the PIN shown by the device."""
        self.pin = pin
        url = (
            f"http://{self.host}:{self.cers_port}/register"
            f"?name={self.nickname}&registrationType=initial"
            f"&deviceId={self.client_id}&wolSupport=true"
        )
        response = requests.get(url, headers=self._auth_headers(), timeout=TIMEOUT)
        if response.status_code != 200:
            self.pin = None
            return False
        return True

    def _cers_get(self, action: str) -> ElementTree.Element:
        if not self.is_paired:
            raise PairingRequired("call complete_pairing() first")
        url = f"http://{self.host}:{self.cers_port}/{action}"
        response = requests.get(url, headers=self._auth_headers(), timeout=TIMEOUT)
        response.raise_for_status()
        return ElementTree.fromstring(response.content)

    def get_remote_commands(self, refresh: bool = False) -> dict[str, str]:
        """Fetch this device's own name->IRCC-code table. Needs pairing."""
        if self._commands is not None and not refresh:
            return self._commands
        root = self._cers_get("getRemoteCommandList")
        self._commands = {
            el.get("name"): el.get("value")
            for el in root.findall("command")
            if el.get("name") and el.get("value")
        }
        return self._commands

    def get_content_information(self) -> dict[str, str]:
        """Current disc/title info (class/source/mediaType/mediaFormat), if
        any. Empty dict with no disc loaded. Needs pairing.
        """
        root = self._cers_get("getContentInformation")
        return {
            item.get("field"): item.get("value")
            for item in root.findall("infoItem")
            if item.get("field")
        }

    def get_status(self) -> dict[str, dict[str, str]]:
        """Device-level status, keyed by status name (e.g. "viewing", "disc").

        Confirmed live 2026-09-07: a "viewing" entry is present while
        content is actively being watched (playing OR paused — this does
        NOT distinguish the two) and absent once you back out to a menu,
        even with the same disc still loaded (a "disc" entry persists
        either way).

        WARNING (2026-09-19): "viewing" has stopped appearing at all. A
        UHD BD-ROM played for over an hour — owner-confirmed, corroborated
        by the projector reporting a live 3840x2160/24p signal — and every
        response across four sampling windows contained only "disc". The
        polling client was verified healthy throughout (~10 s cadence, all
        successful, "disc" parsed correctly from the same responses), so
        this is the device's answer, not a fetch failure. Suspected cause
        is a firmware update; no version was captured on 2026-09-07 to
        diff against. Do not build new work on "viewing" — use the DIAL
        app-state probe (port 50202, unauthenticated, no pairing). Full
        write-up in docs/PROTOCOL.md.

        AVTransport and IRCC's X_GetStatus remain ruled out as playback
        signals — AVTransport was re-tested 2026-09-19 during confirmed
        playback and still returned NO_MEDIA_PRESENT. Needs pairing.
        """
        root = self._cers_get("getStatus")
        result: dict[str, dict[str, str]] = {}
        for status_el in root.findall("status"):
            name = status_el.get("name")
            if not name:
                continue
            result[name] = {
                item.get("field"): item.get("value")
                for item in status_el.findall("statusItem")
                if item.get("field")
            }
        return result

    def is_viewing_content(self) -> bool:
        """True while a movie/disc is actively being watched (playing or
        paused), False once back at a menu. Needs pairing. See get_status().

        WARNING (2026-09-19): this now returns False even during real
        playback — the device stopped emitting the "viewing" entry this
        wraps. The check itself is unchanged and still faithful; it is the
        device behaviour that changed. See get_status() and
        docs/PROTOCOL.md, and prefer the DIAL probe.
        """
        return "viewing" in self.get_status()

    def send_ircc_code(self, code: str) -> None:
        """Send a raw base64 IRCC code (remote-button press). Needs pairing."""
        if not self.is_paired:
            raise PairingRequired("call complete_pairing() first")
        url = f"http://{self.host}:{self.ircc_port}/upnp/control/IRCC"
        action = "urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"
        body = (
            '<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">'
            f"<IRCCCode>{code}</IRCCCode></u:X_SendIRCC>"
        )
        self._soap_request(url, action, body)

    def send_command(self, name: str) -> None:
        """Send a remote-button press by name, e.g. "Play" or "Eject".

        Uses the device's own command list if it's been fetched (see
        get_remote_commands()), otherwise falls back to the known IRCC_CODES
        table. Needs pairing.
        """
        code = (self._commands or IRCC_CODES).get(name)
        if code is None:
            raise ValueError(f"unknown command: {name}")
        self.send_ircc_code(code)

    def play(self) -> None:
        self.send_command("Play")

    def pause(self) -> None:
        self.send_command("Pause")

    def stop(self) -> None:
        self.send_command("Stop")

    def power(self) -> None:
        """Toggle power (no separate on/off code — this is what the remote's power button sends)."""
        self.send_command("Power")

    def eject(self) -> None:
        self.send_command("Eject")

    def wake_on_lan(self, broadcast: str = "255.255.255.255") -> None:
        """Power on from full standby via a WOL magic packet."""
        if not self.mac:
            raise ValueError("mac address not set")
        mac_bytes = bytes.fromhex(self.mac.replace(":", "").replace("-", ""))
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, 9))
