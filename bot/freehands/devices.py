"""Known devices: who owns them, and what the console may say about them.

Some consoles belong to the team rather than to a person. A test bench gets
handed around, so recording where it paired from says nothing useful and
records a home address for no reason. Those devices are identified at claim
time and their address is dropped before it is ever written to disk.

Matching is on `Build.MODEL`, which is stable per hardware model, rather than
on the display name, which the app builds from manufacturer and model and can
therefore drift.
"""

from __future__ import annotations

from dataclasses import dataclass

CHIMERA_TEAM = "ChimeraTeam"


@dataclass(frozen=True)
class KnownDevice:
    """A device model the console knows by name."""

    model: str
    manufacturer: str
    owner: str
    # Shown instead of the address in `+devices`.
    label: str
    # Test hardware: `+devices` says so explicitly and hides its address.
    testing: bool = False
    # A sticker the app draws beside the device name.
    sticker: str = ""

    def describe(self) -> str:
        """The line `+devices` prints where a location would go."""
        if self.testing:
            return f"testing device owned by {self.owner}"
        return f"device owned by {self.owner}"


KNOWN_DEVICES: tuple[KnownDevice, ...] = (
    # Amazon Fire tablet: the shared test bench.
    KnownDevice(
        model="KFTRWI",
        manufacturer="amazon",
        owner=CHIMERA_TEAM,
        label="Test bench",
        testing=True,
        sticker="freehands",
    ),
    # Samsung Galaxy J3 Star: a team phone.
    KnownDevice(
        model="SM-J337T",
        manufacturer="samsung",
        owner=CHIMERA_TEAM,
        label="Team phone",
        sticker="freehands",
    ),
)


def identify(model: str, manufacturer: str = "", name: str = "") -> KnownDevice | None:
    """The known device this is, or None.

    Falls back to the display name so a device paired by an older build, which
    only sent `"Amazon KFTRWI"`, is still recognised.
    """
    probe_model = (model or "").strip().upper()
    probe_maker = (manufacturer or "").strip().lower()
    probe_name = (name or "").strip().upper()

    for device in KNOWN_DEVICES:
        if probe_model and probe_model == device.model:
            if not probe_maker or probe_maker == device.manufacturer:
                return device
        # Older app builds send only the combined display name.
        if not probe_model and device.model in probe_name:
            return device
    return None


def label_for(device: KnownDevice | None) -> str:
    return device.describe() if device else ""
