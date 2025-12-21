from datetime import timedelta
from typing import Any, TypeVar

from pydantic import BaseModel
from qdash.common.datetime_utils import now, to_datetime

T = TypeVar("T", bound=BaseModel)


def _process_data(
    raw_data: dict[str, Any],
    field_map: dict[str, str],
    model_cls: type[T],
    within_24hrs: bool = False,
    cutoff_hours: int = 24,
) -> T:
    result = model_cls()
    if not raw_data:
        return result

    current_time = now()
    cutoff = current_time - timedelta(hours=cutoff_hours)

    for key, value in raw_data.items():
        calibrated_at = value.get("calibrated_at")
        is_recent = True
        if within_24hrs:
            if calibrated_at:
                try:
                    calibrated_at_dt = to_datetime(calibrated_at)
                    if calibrated_at_dt is not None:
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
