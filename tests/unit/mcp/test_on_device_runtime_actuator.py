"""Contract tests for the first-party phone-local MCP actuator."""

import asyncio

from artemis.mcp.action_manifest import DEVICE_ACTIONS, MIN_EXTENSION_DESCRIPTION_LENGTH
from artemis.mcp.actuators.on_device_runtime import OnDeviceRuntimeActuator


def test_runtime_actuator_exposes_canonical_actions_and_typed_extensions() -> None:
    actuator = object.__new__(OnDeviceRuntimeActuator)

    assert actuator.capabilities() == DEVICE_ACTIONS
    extensions = actuator.extensions()
    assert {extension.name for extension in extensions} == {
        "get_runtime_capabilities",
        "get_device_info",
        "list_apps",
        "open_settings",
    }
    assert all(len(extension.description) >= MIN_EXTENSION_DESCRIPTION_LENGTH for extension in extensions)
    assert all(extension.targets == frozenset({"operator", "flash", "validator"}) for extension in extensions)
    assert all(callable(extension.handler) for extension in extensions)


def test_force_stop_fails_closed_without_initializing_a_driver() -> None:
    actuator = object.__new__(OnDeviceRuntimeActuator)
    result = asyncio.run(actuator.manage_app("stop", "com.example.app"))

    assert result.ok is False
    assert "without ADB or root" in result.message
