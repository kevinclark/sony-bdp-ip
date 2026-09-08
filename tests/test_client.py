from unittest.mock import MagicMock, patch

import pytest

from sony_bdp_ip import PairingRequired, SonyBdpClient, TransportState


def make_client(**kwargs):
    kwargs.setdefault("mac", "88:c9:e8:61:66:c5")
    return SonyBdpClient(host="192.168.1.50", **kwargs)


def test_transport_state_from_str_known():
    assert TransportState.from_str("PLAYING") is TransportState.PLAYING


def test_transport_state_from_str_unknown_falls_back():
    assert TransportState.from_str("SOMETHING_NEW") is TransportState.UNKNOWN


def test_is_paired_false_before_pairing():
    client = make_client()
    assert client.is_paired is False


def test_auth_headers_omit_authorization_when_unpaired():
    client = make_client()
    headers = client._auth_headers()
    assert "Authorization" not in headers
    assert headers["X-CERS-DEVICE-ID"] == client.client_id


def test_auth_headers_include_basic_auth_once_paired():
    client = make_client()
    client.pin = "1234"
    headers = client._auth_headers()
    assert headers["Authorization"].startswith("Basic ")


def test_cers_get_requires_pairing():
    client = make_client()
    with pytest.raises(PairingRequired):
        client._cers_get("getStatus")


def test_send_command_requires_pairing():
    client = make_client()
    with pytest.raises(PairingRequired):
        client.play()


def test_send_command_unknown_name_raises():
    client = make_client()
    client.pin = "1234"
    with pytest.raises(ValueError):
        client.send_command("NotARealButton")


def test_wake_on_lan_without_mac_raises():
    client = make_client(mac=None)
    with pytest.raises(ValueError):
        client.wake_on_lan()


def test_wake_on_lan_sends_magic_packet():
    client = make_client()
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__.return_value = mock_sock
        client.wake_on_lan(broadcast="192.168.1.255")

    mac_bytes = bytes.fromhex("88c9e86166c5")
    expected_packet = b"\xff" * 6 + mac_bytes * 16
    mock_sock.sendto.assert_called_once_with(expected_packet, ("192.168.1.255", 9))


def test_get_status_parses_viewing_entry():
    client = make_client()
    client.pin = "1234"
    xml = b"""<response>
        <status name="viewing">
            <statusItem field="class" value="video"/>
        </status>
        <status name="disc">
            <statusItem field="mediaType" value="BD"/>
        </status>
    </response>"""
    mock_response = MagicMock()
    mock_response.content = xml
    mock_response.status_code = 200
    with patch("requests.get", return_value=mock_response):
        status = client.get_status()

    assert status == {
        "viewing": {"class": "video"},
        "disc": {"mediaType": "BD"},
    }


def test_is_viewing_content_true_when_viewing_present():
    client = make_client()
    client.pin = "1234"
    xml = b'<response><status name="viewing"></status></response>'
    mock_response = MagicMock()
    mock_response.content = xml
    with patch("requests.get", return_value=mock_response):
        assert client.is_viewing_content() is True


def test_is_viewing_content_false_at_menu():
    client = make_client()
    client.pin = "1234"
    xml = b'<response><status name="disc"></status></response>'
    mock_response = MagicMock()
    mock_response.content = xml
    with patch("requests.get", return_value=mock_response):
        assert client.is_viewing_content() is False


def test_get_transport_state_unknown_when_missing_element():
    client = make_client()
    xml = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
        <s:Body></s:Body>
    </s:Envelope>"""
    mock_response = MagicMock()
    mock_response.content = xml
    with patch("requests.post", return_value=mock_response):
        assert client.get_transport_state() is TransportState.UNKNOWN


def test_send_command_uses_device_command_table_over_default():
    client = make_client()
    client.pin = "1234"
    client._commands = {"Play": "custom-code"}
    with patch.object(client, "send_ircc_code") as mock_send:
        client.play()
    mock_send.assert_called_once_with("custom-code")
