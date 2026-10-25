"""Direct phone-local client for the first-party ARTEMIS Android Runtime.

Enabled only with ARTEMIS_ON_DEVICE_RUNTIME=1. It deliberately accepts only a
loopback URL because the Android runtime exposes powerful UI controls. The
phone-generated bearer token is required; this path does not use adb forward,
adb pairing, or the host-side helper-token broadcast.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote, urlsplit
import urllib.error
import urllib.request
from typing import Any

from artemis.clients.accessibility_client import AccessibilityClient, HelperUnavailable, _dimensions
from artemis.runtime.helper_manager import HelperSession
from third_party.mobile_use.clients.ui_automator_client import UIAutomatorScreenData
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

TOKEN_ENV = "ARTEMIS_RUNTIME_TOKEN"
URL_ENV = "ARTEMIS_RUNTIME_URL"
DEFAULT_URL = "http://127.0.0.1:18888"


class OnDeviceRuntimeManager:
    """Minimal helper-manager-compatible transport with no ADB dependencies."""

    def __init__(self) -> None:
        self.token = os.environ.get(TOKEN_ENV, "").strip()
        self.base_url = os.environ.get(URL_ENV, DEFAULT_URL).strip() or DEFAULT_URL
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError(
                f"{URL_ENV} must use local loopback HTTP (127.0.0.1 or localhost); "
                "the Android Runtime intentionally does not accept a remote host."
            )
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(f"{URL_ENV} must contain only scheme, loopback host, and port.")
        self.port = parsed.port or 18888
        if not self.token:
            raise ValueError(
                f"{TOKEN_ENV} is missing. Open ARTEMIS Runtime on the phone and copy its "
                "local pairing token into your Termux environment or private .env file."
            )

    def host_token(self) -> str:
        return self.token

    def attach(
        self,
        serial: str,
        *,
        provision: bool = False,
        on_event: Any = None,
        revive: bool | None = None,
    ) -> HelperSession:
        # This is a local app endpoint, not an ADB serial. No install/enable/forward is attempted.
        return HelperSession(
            serial=serial,
            local_port=self.port,
            transport_id=None,
            version_code=8,
            version_name="1.3.1",
            owns_forward=False,
            token=self.token,
            protocol_version=2,
        )

    def reattach(self, serial: str) -> HelperSession:
        return self.attach(serial, provision=False)

    def detach(self, serial: str) -> None:
        return None

    def push_token(self, serial: str) -> bool:
        # Unlike USB mode, local mode receives its token from the app UI; never attempt ADB.
        return bool(self.token)

    def ping(self, local_port: int) -> dict[str, Any] | None:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/ping",
                headers={"X-Artemis-Token": self.token},
            )
            with urllib.request.urlopen(req, timeout=2.0) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) and data.get("success") else None
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            return None


class OnDeviceRuntimeClient(AccessibilityClient):
    """AccessibilityClient wire protocol pointed directly at the phone-local app."""

    backend_name = "on-device-runtime"

    def __init__(self, device_id: str) -> None:
        manager = OnDeviceRuntimeManager()
        super().__init__(
            device_id=device_id,
            manager=manager,  # implements the manager protocol used by AccessibilityClient
            provision_on_connect=False,
            request_timeout=8.0,
        )

    def connect(self, on_event: Any = None) -> None:
        # Do not call ensure_device_awake(): that helper uses ADB. This mode must be ADB-free.
        self._session = self._manager.attach(self._device_id, provision=False)
        raw = self._http("/capabilities")
        payload = json.loads(raw.decode("utf-8"))
        if not payload.get("success"):
            self._session = None
            raise HelperUnavailable("ARTEMIS Runtime did not confirm its capabilities.")
        self.runtime_capabilities = payload
        logger.info(
            f"Connected to the phone-local ARTEMIS Runtime at 127.0.0.1:{self._session.local_port}."
        )

    def get_screen_data(self) -> UIAutomatorScreenData:
        """Capture a screen snapshot without ever falling back to host-side ADB."""

        snapshot = self._snapshot()
        xml, elements = self._elements_from_dump(snapshot)
        if not snapshot.get("has_screenshot") or not snapshot.get("screenshot_base64"):
            reason = snapshot.get("screenshot_error") or "the runtime returned no screenshot"
            raise RuntimeError(
                "The phone-local Runtime could not capture a screenshot: "
                f"{reason}. This mode requires Android 11+ screenshot access."
            )
        width, height = _dimensions(snapshot)
        return UIAutomatorScreenData(
            base64=str(snapshot["screenshot_base64"]),
            hierarchy_xml=xml,
            elements=elements,
            width=width,
            height=height,
        )

    def get_screenshot(self):
        """Return a screenshot from the phone-local service, never via ADB."""
        import base64
        from io import BytesIO
        from PIL import Image

        snapshot = self._snapshot()
        if not snapshot.get("has_screenshot") or not snapshot.get("screenshot_base64"):
            return None
        return Image.open(BytesIO(base64.b64decode(snapshot["screenshot_base64"]))).copy()

    def get_capabilities(self) -> dict[str, Any]:
        """Return authenticated runtime capability metadata."""
        data = json.loads(self._http("/capabilities").decode("utf-8"))
        if not isinstance(data, dict) or not data.get("success"):
            raise HelperUnavailable("ARTEMIS Runtime capability discovery failed.")
        self.runtime_capabilities = data
        return data

    def get_device_info(self) -> dict[str, Any]:
        """Read device/runtime diagnostics without ADB or shell access."""
        data = json.loads(self._http("/device").decode("utf-8"))
        if not isinstance(data, dict) or not data.get("success"):
            raise HelperUnavailable(
                f"ARTEMIS Runtime device diagnostics failed: "
                f"{data.get('error', 'invalid response') if isinstance(data, dict) else 'invalid response'}"
            )
        return data

    def list_apps(self, query: str = "") -> dict[str, Any]:
        """List launchable apps only; Android package visibility limits the inventory."""
        path = "/apps"
        if query.strip():
            path += "?q=" + quote(query.strip(), safe="")
        data = json.loads(self._http(path).decode("utf-8"))
        if not isinstance(data, dict) or not data.get("success"):
            raise HelperUnavailable(
                f"ARTEMIS Runtime app discovery failed: "
                f"{data.get('error', 'invalid response') if isinstance(data, dict) else 'invalid response'}"
            )
        if not isinstance(data.get("apps"), list):
            raise HelperUnavailable("ARTEMIS Runtime returned an invalid app inventory.")
        return data

    def open_settings(self, target: str) -> bool:
        """Open a whitelisted Android Settings page; the user controls any changes."""
        return self._rpc("open_settings", {"target": target})

    def open_link(self, url: str) -> bool:
        """Open a web URL using Android's normal activity resolver."""
        return self._rpc("open_link", {"url": url})

    def erase_one_char(self) -> bool:
        """Delete one code point from a focused non-password text field."""
        return self._rpc("erase_one_char", {})

    def click_element(
        self, *, text: str | None = None, view_id: str | None = None, exact: bool = True
    ) -> bool:
        """Click exactly one accessible text label or fully-qualified Android view ID."""
        text_selector = text.strip() if text else ""
        id_selector = view_id.strip() if view_id else ""
        if bool(text_selector) == bool(id_selector):
            return False
        payload: dict[str, Any] = {"exact": bool(exact)}
        if text_selector:
            payload["text"] = text_selector
        else:
            payload["view_id"] = id_selector
        return self._rpc("click_element", payload)

    def press_key(self, key: str) -> bool:
        """Dispatch only native key actions explicitly supported by the runtime."""
        normalized = str(key).strip().lower().replace("keycode.", "").replace("keycode_", "")
        if normalized not in {"enter", "ime_enter", "delete"}:
            return False
        return self._rpc("press_key", {"key": normalized})

    def _ensure_session(self) -> HelperSession:
        if self._session is None:
            self.connect()
        return self._session
