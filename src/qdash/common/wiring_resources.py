"""Hardware module resources shared by scheduling and execution admission."""

from typing import Any


def mux_module_resources(entry: dict[str, Any]) -> set[str]:
    """Return the readout/control module claims used by the CR scheduler.

    Channels on the same module conflict. Keep readout and control namespaces
    separate to preserve the scheduler's existing conflict rules.
    Prefer ':' as the channel separator so module names can contain hyphens;
    retain the legacy first-hyphen separator when ':' is absent.
    """
    resources: set[str] = set()
    read_out = entry.get("read_out")
    if read_out:
        separator = ":" if ":" in read_out else "-"
        resources.add(f"module:read_out:{read_out.split(separator, 1)[0]}")
    for ctrl in entry.get("ctrl", []):
        separator = ":" if ":" in ctrl else "-"
        resources.add(f"module:ctrl:{ctrl.split(separator, 1)[0]}")
    return resources
