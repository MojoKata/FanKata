"""Hardware backends for fankatad.

The controller only talks to a Backend, so the same control loop, restore rules
and Speed pulse run on every platform:

- HwmonBackend: Linux kernel hwmon (sysfs), or a simulated sysfs tree.
- LhmBackend:   Windows, through LibreHardwareMonitorLib and the PawnIO driver.
"""

from __future__ import annotations

from fankata_core.hwmon import Inventory


class BackendError(Exception):
    """A hardware operation failed; the message is shown to the user."""


class Backend:
    name = "backend"
    inv: Inventory

    def describe(self) -> str:
        """Short text for the GUI, e.g. which library/driver is in use."""
        return self.name

    def refresh(self) -> None:
        """Called once per tick before readings are taken."""

    def read_temps(self) -> dict[str, float | None]:
        raise NotImplementedError

    def read_rpms(self) -> dict[str, int | None]:
        raise NotImplementedError

    def read_duty(self, pid: str) -> int | None:
        raise NotImplementedError

    def capture(self, pid: str) -> dict:
        """The channel's default state, recorded before Fankata's first write (requirement 8.1)."""
        return {}

    def take_control(self, pid: str) -> None:
        """Switch the channel to software control. Raises BackendError."""

    def write_duty(self, pid: str, duty: float) -> None:
        """Set the duty cycle in %. Raises BackendError."""
        raise NotImplementedError

    def restore(self, pid: str, original: dict) -> dict:
        """Return the channel to its default state (requirement 8.3). Returns {ok, message}."""
        raise NotImplementedError

    def restore_mode(self, pid: str, original: dict) -> dict:
        """How the channel returns to its default: {mode: auto|fixed|full, duty}."""
        return {"mode": "auto", "duty": None}

    def chips(self) -> list[dict]:
        """Sensor chips for Troubleshoot fans (requirement 4.7): controls, speed inputs, speed-only fans."""
        from fankata_core.troubleshoot import chips_from_inventory
        return chips_from_inventory(self.inv)

    def close(self) -> None:
        pass
