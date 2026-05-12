from qdash.analysis.spectroscopy.estimate_resonator_frequency import (
    Peak,
    PeakGroup,
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


def test_resonance_score_prefers_wider_high_power_x_span() -> None:
    narrow = Resonance(
        high_power_peaks=PeakGroup(
            [
                Peak(x=10, y=4, prominence=1.0),
                Peak(x=11, y=5, prominence=1.0),
            ]
        ),
        low_power_peak=Peak(x=10, y=2, prominence=1.0),
    )
    wide = Resonance(
        high_power_peaks=PeakGroup(
            [
                Peak(x=20, y=4, prominence=1.0),
                Peak(x=24, y=5, prominence=1.0),
            ]
        ),
        low_power_peak=Peak(x=20, y=2, prominence=1.0),
    )

    assert wide.high_power_x_span == 4.0
    assert narrow.high_power_x_span == 1.0
    assert wide.score > narrow.score
