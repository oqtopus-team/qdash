import math

from qdash.common.agent_gate import evaluate_numeric_candidate


def test_numeric_gate() -> None:
    assert evaluate_numeric_candidate(1.0, minimum=1.0, maximum=2.0).accepted
    assert not evaluate_numeric_candidate(math.nan).accepted
    assert not evaluate_numeric_candidate(0.9, minimum=1.0).accepted
    assert not evaluate_numeric_candidate(2.1, maximum=2.0).accepted
