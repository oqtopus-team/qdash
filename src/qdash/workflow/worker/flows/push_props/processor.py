import pendulum
from pydantic import BaseModel


def _process_data(
    raw_data: dict,
    field_map: dict[str, str],
    model_cls: type[BaseModel],
    within_24hrs: bool = False,
) -> BaseModel:
    result = model_cls()
    if not raw_data:
        return result

    now = pendulum.now("Asia/Tokyo")
    cutoff = now.subtract(hours=24)

    for key, value in raw_data.items():
        calibrated_at = value.get("calibrated_at")
        is_recent = True
        if within_24hrs and calibrated_at:
            try:
                calibrated_at_dt = pendulum.parse(calibrated_at, tz="Asia/Tokyo")
                is_recent = calibrated_at_dt >= cutoff
            except Exception:
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
