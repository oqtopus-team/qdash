from qdash.common.config.metrics import (
    MetricMetadata,
    MetricsConfig,
    load_metrics_config,
)


def test_metric_metadata_category_is_optional() -> None:
    metadata = MetricMetadata(
        title="T1",
        unit="μs",
        scale=1,
        evaluation={"mode": "maximize"},
    )

    assert metadata.category is None


def test_metric_metadata_accepts_category() -> None:
    metadata = MetricMetadata(
        title="T1",
        unit="μs",
        scale=1,
        category="Coherence",
        evaluation={"mode": "maximize"},
    )

    assert metadata.category == "Coherence"


def test_load_metrics_config_parses_categories() -> None:
    config = load_metrics_config()

    assert isinstance(config, MetricsConfig)
    # Every qubit and coupling metric in the shipped config defines a category.
    for metadata in config.qubit_metrics.values():
        assert metadata.category, "qubit metric is missing a category"
    for metadata in config.coupling_metrics.values():
        assert metadata.category, "coupling metric is missing a category"

    assert config.qubit_metrics["t1"].category == "Coherence"
    assert config.coupling_metrics["static_zz_interaction"].category == "Interaction"
