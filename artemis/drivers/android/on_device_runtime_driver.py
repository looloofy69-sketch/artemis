"""Android device driver backed by the first-party phone-local ARTEMIS Runtime.

Core UI interactions use the native AccessibilityService endpoint. Shell commands
are available only when Root Mode is explicitly enabled in the runtime app on a
rooted device. Screen video recording is intentionally unsupported in this mode.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Literal

from artemis.clients.on_device_runtime_client import OnDeviceRuntimeClient
from artemis.drivers.android.adb_driver import AndroidAdbDriver
from artemis.drivers.base import KeyCode, ScreenData, SwipeDirection
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


class OnDeviceRuntimeDriver(AndroidAdbDriver):
    """Driver that uses ARTEMIS Runtime's local HTTP API instead of ADB actions."""

    def __init__(self, device_id: str, adb_client: Any, ui_adb_client: Any = None,
                 width: int = 1080, height: int = 2340):
        runtime_client = ui_adb_client or OnDeviceRuntimeClient(device_id)
        super().__init__(
            device_id=device_id,
            adb_client=adb_client,
            ui_adb_client=runtime_client,
            width=width,
            height=height,
        )

    @property
    def runtime_client(self) -> OnDeviceRuntimeClient:
        return self._ui_adb_client

    async def connect(self) -> None:
        await asyncio.to_thread(self.runtime_client.connect)
        logger.info("Connected using phone-local ARTEMIS Runtime; no ADB device is required.")

    async def disconnect(self) -> None:
        if self._ui_adb_client is not None:
            await asyncio.to_thread(self._ui_adb_client.disconnect)

    async def tap(self, x: int, y: int, duration_ms: int = 100,
                  times: int = 1, delay_ms: int = 100) -> bool:
        if duration_ms >= 500:
            return bool(self.runtime_client._rpc(
                "long_press", {"x": x, "y": y, "duration": min(duration_ms, 5000)}
            ))
        for index in range(max(1, min(times, 10))):
            if not self.runtime_client.tap(x, y):
                return False
            if index + 1 < times:
                await asyncio.sleep(max(0, min(delay_ms, 2000)) / 1000)
        return True

    async def long_press(self, x: int, y: int, duration_ms: int = 1000) -> bool:
        return bool(self.runtime_client._rpc(
            "long_press", {"x": x, "y": y, "duration": min(max(duration_ms, 500), 5000)}
        ))

    async def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int,
                    duration_ms: int = 800) -> bool:
        return bool(self.runtime_client.swipe(start_x, start_y, end_x, end_y, duration_ms))

    async def input_text(self, text: str, clear_existing: bool = True) -> bool:
        if clear_existing and not self.runtime_client.clear_text():
            return False
        return bool(self.runtime_client.send_text(text))

    async def press_key(self, key: KeyCode | str | int) -> bool:
        value = key.value if isinstance(key, KeyCode) else str(key)
        name = value.lower().replace("keycode.", "").replace("keycode_", "")
        global_actions = {
            "home": "home",
            "back": "back",
            "app_switch": "recents",
            "recents": "recents",
            "notifications": "notifications",
            "quick_settings": "quick_settings",
            "power_dialog": "power_dialog",
            "lock_screen": "lock_screen",
        }
        if name in global_actions:
            return bool(self.runtime_client._rpc("global", {"action": global_actions[name]}))
        # Non-global key events require shell input, which is intentionally not
        # simulated as a privileged operation on stock Android.
        logger.warning(f"Key action '{name}' is not supported in non-root runtime mode.")
        return False

    async def launch_app(self, package_name: str) -> bool:
        return bool(self.runtime_client._rpc("launch_app", {"package": package_name}))

    async def stop_app(self, package_name: str) -> bool:
        return bool(self.runtime_client._rpc("stop_app", {"package": package_name}))

    async def get_current_package(self) -> str | None:
        try:
            raw = self.runtime_client._http("/ping")
            data = json.loads(raw.decode("utf-8"))
            value = data.get("package")
            return str(value) if value else None
        except Exception as exc:
            logger.debug(f"Could not read foreground package from ARTEMIS Runtime: {exc}")
            return None

    async def execute_shell(self, command: str, timeout_seconds: float = 15.0) -> str:
        # This endpoint rejects requests unless Root Mode has been explicitly enabled in the app.
        payload = {"command": command, "timeout_ms": int(max(250, min(timeout_seconds, 10.0)) * 1000)}
        try:
            raw = self.runtime_client._http("/root/exec", payload=payload, timeout=timeout_seconds + 2)
            response = json.loads(raw.decode("utf-8"))
            if not response.get("success"):
                return f"Error: {response.get('error') or response.get('output') or 'root command failed'}"
            return str(response.get("output", ""))
        except Exception as exc:
            return f"Error: {exc}"

    async def start_video_recording(self, output_dir: Path | None = None) -> None:
        raise RuntimeError(
            "Video recording is not implemented for phone-local runtime mode yet. "
            "Run with --without-video-recording-tools."
        )

    async def stop_video_recording(self) -> str | None:
        return None
