"""IP control client for Sony BDP-CE Blu-ray players (e.g. UBP-X700).

Protocol details are documented in docs/PROTOCOL.md. In short: playback
state comes from a standard, unauthenticated UPnP AVTransport service.
Actual remote control (play/pause/power/etc.) goes through a Sony-specific
IRCC service that requires a one-time PIN pairing.
"""

from __future__ import annotations

import base64
import socket
from dataclasses import dataclass, field
from enum import Enum
from xml.etree import ElementTree

import requests

DEFAULT_IRCC_PORT = 50001
DEFAULT_CERS_PORT = 50002
DEFAULT_DMR_PORT = 52323
TIMEOUT = 5

_SOAP_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>{body}</s:Body>
</s:Envelope>"""

_NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "avt": "urn:schemas-upnp-org:service:AVTransport:1",
    "ircc": "urn:schemas-sony-com:service:IRCC:1",
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
        client_id: str = "home-assistant",
        nickname: str = "Home Assistant",
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
        """Query play/pause/stop state. Needs no pairing."""
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

        The device should show a PIN somewhere (front panel or on-screen
        display) after this call — pass it to complete_pairing().
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

    def wake_on_lan(self, broadcast: str = "255.255.255.255") -> None:
        """Power on from full standby via a WOL magic packet."""
        if not self.mac:
            raise ValueError("mac address not set")
        mac_bytes = bytes.fromhex(self.mac.replace(":", "").replace("-", ""))
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, 9))
