"""MCP actuator bound to ARTEMIS's first-party phone-local Android Runtime.

The canonical MCP schemas stay shared with the ADB backend. Only the mechanism
that performs physical actions changes: screenshots, gestures and text use the
native AccessibilityService endpoint on 127.0.0.1, with no ADB forwarding.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit
from typing import Any

from artemis.drivers.factory import get_driver
from artemis.mcp.action_manifest import DEVICE_ACTIONS, ExtensionTool
from artemis.mcp.action_types import ActionCode, ActionResult
from artemis.mcp.actuators.adb import AdbActuator


class OnDeviceRuntimeActuator(AdbActuator):
    """Reuse ARTEMIS's canonical MCP tools through the local native driver."""

    def capabilities(self) -> frozenset[str]:
        return DEVICE_ACTIONS

    def extensions(self) -> list[ExtensionTool]:
        """Additional read-only discovery tools and safe Settings navigation."""
        targets = frozenset({"operator", "flash", "validator"})
        return [
            ExtensionTool(
                name="get_runtime_capabilities",
                description=(
                    "Read the phone-local ARTEMIS runtime capability report before planning device actions. "
                    "Use it to adapt to unsupported operations; it does not grant permissions or root."
                ),
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_get_runtime_capabilities,
                targets=targets,
            ),
            ExtensionTool(
                name="get_device_info",
                description=(
                    "Read non-secret device diagnostics such as Android version, model, display dimensions, "
                    "rotation and current foreground activity. Use before coordinate-sensitive actions."
                ),
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=self._tool_get_device_info,
                targets=targets,
            ),
            ExtensionTool(
                name="list_apps",
                description=(
                    "List launchable apps visible to Android's launcher query, optionally filtered by name or "
                    "package. Use to resolve a human app name before manage_app; this is not a complete inventory "
                    "of hidden or non-launchable packages."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional app label/package filter.",
                        }
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_list_apps,
                targets=targets,
            ),
            ExtensionTool(
                name="click_element",
                description=(
                    "Click one visible accessible UI node by its exact text label or a fully-qualified Android "
                    "view ID such as com.example:id/submit. Use view IDs for stable selectors and text for readable "
                    "labels; provide exactly one selector. This avoids fragile guessed screen coordinates."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Accessible label text to match."},
                        "view_id": {"type": "string", "description": "Fully-qualified Android view ID."},
                        "exact": {
                            "type": "boolean",
                            "description": "Require exact text equality; ignored for view_id.",
                        },
                    },
                    "additionalProperties": False,
                },
                handler=self._tool_click_element,
                targets=targets,
            ),
            ExtensionTool(
                name="open_settings",
                description=(
                    "Open an allowlisted Android Settings page for a user-visible, user-confirmed change. "
                    "Allowed targets are accessibility, applications, display, wifi, wireless, bluetooth, "
                    "developer_options, location, notifications, sound and date_time; it cannot silently grant settings."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "enum": [
                                "accessibility",
                                "applications",
                                "display",
                                "wifi",
                                "wireless",
                                "bluetooth",
                                "developer_options",
                                "location",
                                "notifications",
                                "sound",
                                "date_time",
                            ],
                        }
                    },
                    "required": ["target"],
                    "additionalProperties": False,
                },
                handler=self._tool_open_settings,
                targets=targets,
            ),
        ]

    async def _tool_get_runtime_capabilities(self) -> str:
        driver = self._runtime_driver()
        data = await asyncio.to_thread(driver.runtime_client.get_capabilities)
        return json.dumps(data, ensure_ascii=False)

    async def _tool_get_device_info(self) -> str:
        data = await self._runtime_driver().get_device_info()
        return json.dumps(data, ensure_ascii=False)

    async def _tool_list_apps(self, query: str = "") -> str:
        data = await self._runtime_driver().list_apps(query)
        return json.dumps(data, ensure_ascii=False)

    async def _tool_click_element(
        self,
        text: str | None = None,
        view_id: str | None = None,
        exact: bool = True,
    ) -> str:
        text_selector = text.strip() if text else ""
        id_selector = view_id.strip() if view_id else ""
        if bool(text_selector) == bool(id_selector):
            return json.dumps(
                {"success": False, "error": "Provide exactly one of text or view_id."},
                ensure_ascii=False,
            )
        success = await self._runtime_driver().click_element(
            text=text_selector or None, view_id=id_selector or None, exact=exact
        )
        return json.dumps(
            {
                "success": success,
                "selector_type": "text" if text_selector else "view_id",
                "selector": text_selector or id_selector,
                "exact": bool(exact),
                "error": None if success else "No visible, enabled, accessible matching node could be clicked.",
            },
            ensure_ascii=False,
        )

    async def _tool_open_settings(self, target: str) -> str:
        success = await self._runtime_driver().open_settings(target)
        return json.dumps(
            {
                "success": success,
                "target": target,
                "message": "Opened Android Settings."
                if success
                else "Android Settings target was unsupported or could not be opened.",
            },
            ensure_ascii=False,
        )

    def _runtime_driver(self) -> Any:
        driver = get_driver(self.ctx)
        if not hasattr(driver, "runtime_client"):
            raise RuntimeError(
                "ARTEMIS_ON_DEVICE_RUNTIME=1 did not produce the phone-local runtime driver."
            )
        return driver

    def _dims(self) -> tuple[int, int]:
        try:
            width, height = self._runtime_driver().screen_size
            if width > 0 and height > 0:
                return int(width), int(height)
        except Exception:
            pass
        return super()._dims()

    @staticmethod
    def _valid_normalized_point(x: int, y: int) -> bool:
        return 0 <= int(x) <= 1000 and 0 <= int(y) <= 1000

    async def click_sequence(
        self, points: list[tuple[int, int]], delay_ms: int = 50
    ) -> ActionResult:
        driver = self._runtime_driver()
        outcomes: list[str] = []
        bounded_delay = max(0, min(int(delay_ms), 2000))
        for index, (nx, ny) in enumerate(points):
            if not self._valid_normalized_point(nx, ny):
                return ActionResult.failure(
                    "click_sequence",
                    f"Invalid normalized coordinate at step {index + 1}: [{nx}, {ny}].",
                    code=ActionCode.INVALID_ARGS,
                )
            x, y = self._to_px(nx, ny)
            if not await driver.tap(x, y):
                return ActionResult.failure(
                    "click_sequence",
                    f"Native runtime rejected tap at step {index + 1} ({nx}, {ny}).",
                    code=ActionCode.DEVICE_ERROR,
                )
            outcomes.append(f"[{nx}, {ny}]")
            if index < len(points) - 1:
                await asyncio.sleep(bounded_delay / 1000)
        return ActionResult.success(
            "click_sequence", f"Tapped in sequence at {'; '.join(outcomes)} (normalized)."
        )

    async def click(self, nx: int, ny: int, times: int = 1, delay_ms: int = 100) -> ActionResult:
        if not self._valid_normalized_point(nx, ny):
            return ActionResult.failure(
                "click",
                "Target must be normalized [x, y] values from 0 to 1000.",
                code=ActionCode.INVALID_ARGS,
            )
        x, y = self._to_px(nx, ny)
        success = await self._runtime_driver().tap(
            x, y, times=max(1, min(int(times), 10)), delay_ms=max(0, min(int(delay_ms), 2000))
        )
        if not success:
            return ActionResult.failure(
                "click",
                f"Native runtime rejected tap at [{nx}, {ny}].",
                code=ActionCode.DEVICE_ERROR,
                normalized_coordinates=[int(nx), int(ny)],
            )
        return ActionResult.success(
            "click",
            f"Tapped at [{nx}, {ny}] (normalized).",
            normalized_coordinates=[int(nx), int(ny)],
        )

    async def long_press(self, nx: int, ny: int, duration_ms: int = 1000) -> ActionResult:
        if not self._valid_normalized_point(nx, ny):
            return ActionResult.failure(
                "long_press",
                "Target must be normalized [x, y] values from 0 to 1000.",
                code=ActionCode.INVALID_ARGS,
            )
        x, y = self._to_px(nx, ny)
        duration = max(500, min(int(duration_ms), 5000))
        success = await self._runtime_driver().long_press(x, y, duration)
        if not success:
            return ActionResult.failure(
                "long_press",
                f"Native runtime rejected long press at [{nx}, {ny}].",
                code=ActionCode.DEVICE_ERROR,
                normalized_coordinates=[int(nx), int(ny)],
            )
        return ActionResult.success(
            "long_press",
            f"Long-pressed at [{nx}, {ny}] for {duration}ms (normalized).",
            normalized_coordinates=[int(nx), int(ny)],
            duration_ms=duration,
        )

    async def input_text(
        self,
        text: str,
        target: tuple[int, int] | None = None,
        clear_exist: bool = True,
    ) -> ActionResult:
        driver = self._runtime_driver()
        coords: list[int] | None = None
        if target is not None:
            nx, ny = int(target[0]), int(target[1])
            if not self._valid_normalized_point(nx, ny):
                return ActionResult.failure(
                    "input_text",
                    "Input target must be normalized [x, y] values from 0 to 1000.",
                    code=ActionCode.INVALID_ARGS,
                )
            x, y = self._to_px(nx, ny)
            coords = [nx, ny]
            if not await driver.tap(x, y):
                return ActionResult.failure(
                    "input_text",
                    f"Could not focus input target at {coords}.",
                    code=ActionCode.DEVICE_ERROR,
                    normalized_coordinates=coords,
                )
        if not await driver.input_text(text, clear_existing=bool(clear_exist)):
            return ActionResult.failure(
                "input_text",
                "Native runtime could not set the focused text field. The field may be unsupported or password-protected.",
                code=ActionCode.DEVICE_ERROR,
                normalized_coordinates=coords,
            )
        return ActionResult.success(
            "input_text",
            "Text entered using the native AccessibilityService.",
            normalized_coordinates=coords,
        )

    async def swipe(
        self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 800
    ) -> ActionResult:
        nx1, ny1 = int(start[0]), int(start[1])
        nx2, ny2 = int(end[0]), int(end[1])
        if not all(self._valid_normalized_point(x, y) for x, y in ((nx1, ny1), (nx2, ny2))):
            return ActionResult.failure(
                "swipe",
                "Swipe endpoints must be normalized [x, y] values from 0 to 1000.",
                code=ActionCode.INVALID_ARGS,
            )
        px1, py1 = self._to_px(nx1, ny1)
        px2, py2 = self._to_px(nx2, ny2)
        duration = max(50, min(int(duration_ms), 5000))
        success = await self._runtime_driver().swipe(px1, py1, px2, py2, duration)
        if not success:
            return ActionResult.failure(
                "swipe", "Native runtime rejected the swipe.", code=ActionCode.DEVICE_ERROR
            )
        return ActionResult.success(
            "swipe",
            f"Swiped from [{nx1}, {ny1}] to [{nx2}, {ny2}] (normalized).",
            normalized_coordinates=[nx1, ny1, nx2, ny2],
            duration_ms=duration,
        )

    async def press_key(self, key: str) -> ActionResult:
        value = str(key).strip()
        if not value:
            return ActionResult.failure(
                "press_key", "Key name is empty.", code=ActionCode.INVALID_ARGS
            )
        if not await self._runtime_driver().press_key(value):
            return ActionResult.failure(
                "press_key",
                f"Key '{value}' is not supported by the phone-local runtime or Android declined it.",
                code=ActionCode.DEVICE_ERROR,
            )
        return ActionResult.success("press_key", f"Executed supported key/global action '{value}'.")

    async def manage_app(self, action: str, app_name: str) -> ActionResult:
        operation = str(action).strip().lower()
        requested = str(app_name).strip()
        if operation == "stop":
            return ActionResult.failure(
                "manage_app",
                "Force-stop is unavailable in phone-local mode without ADB or root. Use Home/Recents or open Android App info for a user-confirmed stop.",
                code=ActionCode.DEVICE_ERROR,
            )
        if operation != "launch" or not requested:
            return ActionResult.failure(
                "manage_app",
                "Use action='launch' and provide an app label or package.",
                code=ActionCode.INVALID_ARGS,
            )
        driver = self._runtime_driver()
        try:
            inventory = await driver.list_apps(requested)
            apps = inventory.get("apps", [])
            needle = requested.casefold()
            exact = [
                app
                for app in apps
                if str(app.get("package", "")).casefold() == needle
                or str(app.get("label", "")).casefold() == needle
            ]
            candidates = exact or list(apps)
            if not candidates:
                return ActionResult.failure(
                    "manage_app",
                    f"No launchable app matched '{requested}'.",
                    code=ActionCode.PACKAGE_NOT_FOUND,
                )
            if len(candidates) > 1:
                labels = ", ".join(
                    f"{app.get('label')} ({app.get('package')})" for app in candidates[:8]
                )
                return ActionResult.failure(
                    "manage_app",
                    f"App name '{requested}' is ambiguous. Use a full package name. Matches: {labels}",
                    code=ActionCode.INVALID_ARGS,
                )
            package = str(candidates[0]["package"])
            if not await driver.launch_app(package):
                return ActionResult.failure(
                    "manage_app",
                    f"Android did not launch '{candidates[0].get('label', package)}'.",
                    code=ActionCode.DEVICE_ERROR,
                )
            return ActionResult.success(
                "manage_app",
                f"Requested launch of '{candidates[0].get('label', package)}' ({package}) through Android's launcher intent.",
            )
        except Exception as exc:
            return ActionResult.failure(
                "manage_app",
                f"Native app discovery/launch failed: {exc}",
                code=ActionCode.DEVICE_ERROR,
                detail=repr(exc),
            )

    async def open_link(self, url: str) -> ActionResult:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ActionResult.failure(
                "open_link",
                "Only absolute HTTP(S) URLs can be opened.",
                code=ActionCode.INVALID_ARGS,
            )
        success = await self._runtime_driver().open_link(url)
        if not success:
            return ActionResult.failure(
                "open_link",
                "Android could not open this HTTP(S) URL.",
                code=ActionCode.DEVICE_ERROR,
            )
        return ActionResult.success("open_link", f"Asked Android to open '{url}'.")

    async def erase_one_char(self) -> ActionResult:
        if not await self._runtime_driver().erase_one_char():
            return ActionResult.failure(
                "erase_one_char",
                "Deletion was refused: focus a non-password editable field first.",
                code=ActionCode.DEVICE_ERROR,
            )
        return ActionResult.success(
            "erase_one_char", "Deleted one Unicode code point from the focused field."
        )

    async def focus_and_clear_text(self, nx: int, ny: int) -> ActionResult:
        if not self._valid_normalized_point(nx, ny):
            return ActionResult.failure(
                "focus_and_clear_text",
                "Target must be normalized [x, y] values from 0 to 1000.",
                code=ActionCode.INVALID_ARGS,
            )
        x, y = self._to_px(nx, ny)
        driver = self._runtime_driver()
        if not await driver.tap(x, y) or not await driver.runtime_client.clear_text():
            return ActionResult.failure(
                "focus_and_clear_text",
                "Could not focus and clear the target using the native runtime.",
                code=ActionCode.DEVICE_ERROR,
            )
        return ActionResult.success(
            "focus_and_clear_text",
            f"Cleared text at [{nx}, {ny}] (normalized).",
            normalized_coordinates=[int(nx), int(ny)],
        )
