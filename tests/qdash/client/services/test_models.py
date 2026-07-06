from qdash.client.services.models import (
    Condition,
    CrDirection,
    DeviceTopologyRequest,
    FidelityCondition,
)


def test_device_topology_request_serializes_condition_cr_direction() -> None:
    condition = Condition(
        coupling_fidelity=FidelityCondition(min=0.8, max=1.0, is_within_24h=True),
        qubit_fidelity=FidelityCondition(min=0.9, max=1.0, is_within_24h=True),
        readout_fidelity=FidelityCondition(min=0.7, max=1.0, is_within_24h=True),
        cr_direction=CrDirection.mix,
    )
    request = DeviceTopologyRequest(condition=condition)

    assert request.model_dump()["condition"]["cr_direction"] == "mix"
