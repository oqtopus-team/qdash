from qdash.analysis.spectroscopy.estimate_resonator_frequency import (
    Peak,
    Resonance,
    estimate_local_bare_shift_boundary,
    estimate_optimal_powers,
)


def test_estimate_optimal_powers_uses_midpoint_between_minimum_and_local_low_power() -> None:
    ys = [-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0]
    resonance = Resonance(high_power_peaks=None, low_power_peak=Peak(x=10, y=6, prominence=1.0))

    local_boundary = estimate_local_bare_shift_boundary(ys, resonance)
    optimal_powers = estimate_optimal_powers(
        ys,
        [local_boundary],
        minimum_usable_power=-40.0,
    )

    assert local_boundary.low_power == -30.0
    assert optimal_powers == [-35.0]
