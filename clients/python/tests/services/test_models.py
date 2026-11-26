from qdash.client.services.models import (
    AgentChatShareBlockSchema,
    AgentChatShareBlockType,
    Condition,
    CrDirection,
    DashboardPanelModel,
    DeviceTopologyRequest,
    FidelityCondition,
    Type,
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


def test_dashboard_panel_type_keeps_its_name_beside_the_chat_share_block_type() -> None:
    # A new enum elsewhere in the schema must not take the existing ``Type`` export.
    assert Type.qubit_metric.value == "qubit_metric"
    assert DashboardPanelModel.model_fields["type"].annotation is Type
    assert {member.value for member in AgentChatShareBlockType} == {"text", "chart", "ui"}
    assert AgentChatShareBlockSchema.model_fields["type"].annotation is AgentChatShareBlockType
