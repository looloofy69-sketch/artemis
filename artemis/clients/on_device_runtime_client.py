"""Direct phone-local client for the first-party ARTEMIS Android Runtime.

Enabled only with ARTEMIS_ON_DEVICE_RUNTIME=1. It deliberately accepts only a
loopback URL because the Android runtime exposes powerful UI controls. The
phone-generated bearer token is required; this path does not use adb forward,
adb pairing, or the host-side helper-token broadcast.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit
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
            version_code=7,
            version_name="1.3.0",
            owns_forward=False,
            token=self.token,
            protocol_version=3,
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

    def _ensure_session(self) -> HelperSession:
        if self._session is None:
            self.connect()
        return self._session
