import math
from typing import Any

THRESHOLD = 1e3  # Threshold for scientific notation formatting


def format_sci_notation(n: float, exp_step: int = 3) -> str:
    """Format a number in scientific notation with a specified exponent step."""
    exp = math.floor(math.log10(abs(n)))
    exp_n = exp - (exp % exp_step)
    mantissa = n / (10**exp_n)
    return f"{mantissa:.1f}e+{exp_n}"


def format_number(n: float | str) -> float | str:
    """Format a number to scientific notation if it is a float and its absolute value is >= 1e3."""
    if isinstance(n, float) and abs(n) >= THRESHOLD:
        return float(format_sci_notation(n))
    return n


def represent_none(self: Any, _: Any) -> Any:
    """Represent None as a YAML null."""
    return self.represent_scalar("tag:yaml.org,2002:null", "null")


def represent_float(self: Any, data: float) -> Any:
    """Represent a float in YAML, using scientific notation for large values."""
    if abs(data) >= THRESHOLD:
        return self.represent_scalar("tag:yaml.org,2002:float", format_sci_notation(data))
    return self.represent_scalar("tag:yaml.org,2002:float", str(data))
