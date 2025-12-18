from typing import Any

import pendulum
from pydantic import BaseModel


def _process_data(
    raw_data: dict[str, Any],
    field_map: dict[str, str],
    model_cls: type[BaseModel],
    within_24hrs: bool = False,
    cutoff_hours: int = 24,
) -> BaseModel:
    result = model_cls()
    if not raw_data:
        return result

    now = pendulum.now("Asia/Tokyo")
    cutoff = now.subtract(hours=cutoff_hours)

    for key, value in raw_data.items():
        calibrated_at = value.get("calibrated_at")
        is_recent = True
        if within_24hrs:
            if calibrated_at:
                try:
                    calibrated_at_dt = pendulum.parse(calibrated_at, tz="Asia/Tokyo")
                    if isinstance(calibrated_at_dt, pendulum.DateTime):
                        is_recent = calibrated_at_dt >= cutoff
                    else:
                        is_recent = False
                except Exception:
                    is_recent = False
            else:
                # If within_24hrs is True but calibrated_at is missing, exclude the data
                is_recent = False

        v = value.get("value") if is_recent else None
        field = field_map.get(key)
        if v is not None and field:
            if field.startswith("t"):
                v *= 1e3  # us -> ns
            setattr(result, field, v)
        if field == "zx90_gate_fidelity" and v is not None and v > 1.0:
            # Ensure fidelity is within [0, 1]
            v = None
            setattr(result, field, v)

    return result
