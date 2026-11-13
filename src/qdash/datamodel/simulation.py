"""Simulation binding of a chip."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SimulationBindingModel(BaseModel):
    """Marks a chip as a simulated device, fixed when the chip is created from a preset.

    Only the chip creation endpoint writes it, and only for a preset of the deployment's own
    backend. A chip without a binding is treated as unknown hardware: a simulation backend never
    runs it and never writes calibration values to it. A bound chip runs only on its own
    backend and platform, and its values never leave QDash's database (no Qubex YAML, props, or
    GitHub publication).
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["simulation"] = Field("simulation", description="Always 'simulation'")
    backend: str = Field(..., description="Backend that runs the chip, e.g. 'qibocal'")
    preset: str = Field(..., description="Chip preset the chip was created from")
    platform: str = Field(..., description="Simulator platform the chip is bound to")
    template_fingerprint: str = Field(
        ...,
        description=(
            "Structural fingerprint of the platform template at creation: its model, channels, "
            "and pulse shapes without the calibration values QDash owns"
        ),
    )
    bound_at: datetime = Field(..., description="When the binding was created")
