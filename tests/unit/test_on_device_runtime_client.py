"""Tests for the phone-local ARTEMIS Runtime transport boundary."""

import json

import pytest

from artemis.clients.on_device_runtime_client import OnDeviceRuntimeClient, OnDeviceRuntimeManager


def test_runtime_manager_requires_local_pairing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTEMIS_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("ARTEMIS_RUNTIME_URL", raising=False)

    with pytest.raises(ValueError, match="ARTEMIS_RUNTIME_TOKEN"):
        OnDeviceRuntimeManager()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:18888",
        "http://192.0.2.10:18888",
        "http://example.com:18888",
        "http://127.0.0.1:18888/api",
        "http://127.0.0.1:18888/?token=secret",
    ],
)
def test_runtime_manager_rejects_non_loopback_or_ambiguous_urls(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    monkeypatch.setenv("ARTEMIS_RUNTIME_URL", url)

    with pytest.raises(ValueError):
        OnDeviceRuntimeManager()


def test_runtime_manager_uses_local_endpoint_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    monkeypatch.setenv("ARTEMIS_RUNTIME_URL", "http://127.0.0.1:19999")

    manager = OnDeviceRuntimeManager()
    session = manager.attach("artemis-runtime")

    assert session.local_port == 19999
    assert session.base_url == "http://127.0.0.1:19999"
    assert session.token == "test-token"
    assert session.owns_forward is False
    assert session.version_code == 8
    assert session.version_name == "1.3.1"
    assert session.protocol_version == 2


def test_runtime_client_reads_device_diagnostics_and_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    monkeypatch.delenv("ARTEMIS_RUNTIME_URL", raising=False)
    client = OnDeviceRuntimeClient("artemis-runtime")
    requests: list[str] = []

    def fake_http(path: str, payload=None, timeout=None) -> bytes:
        requests.append(path)
        if path == "/capabilities":
            body = {"success": True, "supported_actions": ["tap"], "root_available": False}
        else:
            body = {"success": True, "android_release": "14", "screen_width": 1080,
                    "screen_height": 2400}
        return json.dumps(body).encode("utf-8")

    monkeypatch.setattr(client, "_http", fake_http)
    assert client.get_capabilities()["supported_actions"] == ["tap"]
    info = client.get_device_info()
    assert info["android_release"] == "14"
    assert (info["screen_width"], info["screen_height"]) == (1080, 2400)
    assert requests == ["/capabilities", "/device"]


def test_runtime_client_filters_and_encodes_app_inventory_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    client = OnDeviceRuntimeClient("artemis-runtime")
    seen: list[str] = []

    def fake_http(path: str, payload=None, timeout=None) -> bytes:
        seen.append(path)
        return json.dumps({"success": True, "count": 1, "truncated": False,
                           "apps": [{"label": "Maps", "package": "com.example.maps"}]}).encode()

    monkeypatch.setattr(client, "_http", fake_http)
    result = client.list_apps("Maps & Directions")
    assert result["apps"][0]["package"] == "com.example.maps"
    assert seen == ["/apps?q=Maps%20%26%20Directions"]


def test_runtime_client_rejects_invalid_app_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    client = OnDeviceRuntimeClient("artemis-runtime")
    monkeypatch.setattr(client, "_http", lambda *args, **kwargs: b'{"success":true,"apps":null}')

    with pytest.raises(Exception, match="invalid app inventory"):
        client.list_apps()


def test_runtime_client_dispatches_only_supported_keys_and_settings_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTEMIS_RUNTIME_TOKEN", "test-token")
    client = OnDeviceRuntimeClient("artemis-runtime")
    calls: list[tuple[str, dict]] = []

    def fake_rpc(command: str, params=None) -> bool:
        calls.append((command, params or {}))
        return True

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    assert client.press_key("KEYCODE_ENTER") is True
    assert client.press_key("delete") is True
    assert client.open_settings("accessibility") is True
    assert client.open_link("https://example.org") is True
    assert client.erase_one_char() is True
    assert client.press_key("volume_up") is False
    assert calls == [
        ("press_key", {"key": "enter"}),
        ("press_key", {"key": "delete"}),
        ("open_settings", {"target": "accessibility"}),
        ("open_link", {"url": "https://example.org"}),
        ("erase_one_char", {}),
    ]
