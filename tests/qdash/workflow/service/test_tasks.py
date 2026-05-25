from qdash.workflow.service.tasks import CHECK_1Q_TASKS, FULL_1Q_TASKS_AFTER_CHECK


def test_default_one_qubit_sequences_skip_optimal_readout_amplitude() -> None:
    assert "CheckOptimalReadoutAmplitude" not in CHECK_1Q_TASKS
    assert "CheckOptimalReadoutAmplitude" not in FULL_1Q_TASKS_AFTER_CHECK
