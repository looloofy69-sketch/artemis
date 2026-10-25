"""Select the actuator backend using explicit runtime configuration."""

from __future__ import annotations

import os
from typing import Any

from artemis.context import ArtemisContext
from artemis.controllers.unified_controller import UnifiedMobileController
from artemis.mcp.actuators.adb import AdbActuator


def create_actuator(
    ctx: ArtemisContext,
    controller: UnifiedMobileController | None = None,
) -> AdbActuator:
    """Use the native on-phone actuator only when explicitly opted in."""
    if os.environ.get("ARTEMIS_ON_DEVICE_RUNTIME") == "1":
        from artemis.mcp.actuators.on_device_runtime import OnDeviceRuntimeActuator

        return OnDeviceRuntimeActuator(ctx, controller)
    return AdbActuator(ctx, controller)
