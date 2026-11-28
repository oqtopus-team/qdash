from qdash.client.services.models import (
    AgentChatShareBlockSchema,
    AgentChatShareBlockType,
    Condition,
    CrDirection,
    DashboardPanelModel,
    DecisionId1,
    DeviceTopologyRequest,
    ExecutePipelinePlanRequest,
    ExecutePipelineRequest,
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


def test_pipeline_requests_keep_the_decision_id_type_callers_already_pass() -> None:
    # ExecutePipelineRequest.decision_id was DecisionId1 before stored plans; both run
    # requests share that type so an existing caller's model instance stays valid.
    decision = DecisionId1("d1")
    inline = ExecutePipelineRequest(chip_id="chip-1", spec={}, decision_id=decision)
    plan = ExecutePipelinePlanRequest(
        chip_id="chip-1",
        expected_review_digest="sha256:v1:" + "0" * 64,
        decision_id=decision,
    )
    assert inline.model_dump(mode="json")["decision_id"] == "d1"
    assert plan.model_dump(mode="json")["decision_id"] == "d1"
    for model in (ExecutePipelineRequest, ExecutePipelinePlanRequest):
        assert model.model_fields["decision_id"].annotation == DecisionId1 | None
