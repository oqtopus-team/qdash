import pytest
from pydantic import ValidationError

from qdash.api.schemas.reanalysis import ReanalyzeResonatorSpectroscopyParams
from qdash.api.services.reanalysis_service import ReanalysisService


def test_resonator_assignment_order_accepts_each_mux_offset_once() -> None:
    params = ReanalyzeResonatorSpectroscopyParams(resonator_assignment_order=[0, 3, 1, 2])

    assert params.resonator_assignment_order == [0, 3, 1, 2]


def test_resonator_assignment_order_rejects_duplicate_offsets() -> None:
    with pytest.raises(ValidationError, match=r"each qubit offset 0\.\.3 exactly once"):
        ReanalyzeResonatorSpectroscopyParams(resonator_assignment_order=[0, 0, 1, 2])


def test_reanalysis_reads_legacy_named_assignment_pattern() -> None:
    params = ReanalyzeResonatorSpectroscopyParams()

    assignment_order = ReanalysisService._pick_resonator_assignment_order(
        params,
        {"resonator_assignment_pattern": {"value": "16q", "value_type": "str"}},
    )

    assert assignment_order == [0, 3, 1, 2]
