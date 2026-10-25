"""Tests for the phone-local ARTEMIS Runtime transport boundary."""

import pytest

from artemis.clients.on_device_runtime_client import OnDeviceRuntimeManager


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
