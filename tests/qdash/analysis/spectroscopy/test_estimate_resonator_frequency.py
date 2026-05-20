from qdash.analysis.spectroscopy import BareShiftBoundary
from qdash.analysis.spectroscopy.estimate_resonator_frequency import (
    ComposeResonancesConfig,
    EstimateResonatorFrequencyConfig,
    GroupResonancesConfig,
    Peak,
    PeakGroup,
    Resonance,
    _needs_diverse_reselection,
    _refine_high_power_only_resonance_x,
    _select_diverse_resonances,
    _select_local_resonance,
    _select_resonances,
    estimate_local_bare_shift_boundary,
    estimate_optimal_powers,
)
from qdash.analysis.spectroscopy.mux import guess_sorted_slots_for_partial_mux


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


def test_estimate_optimal_powers_rounds_midpoint_up_when_between_grid_points() -> None:
    ys = [-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0]
    local_boundary = BareShiftBoundary(
        high_power_min=-20.0,
        high_power_max=0.0,
        low_power=-25.0,
    )

    optimal_powers = estimate_optimal_powers(
        ys,
        [local_boundary],
        minimum_usable_power=-40.0,
    )

    assert optimal_powers == [-30.0]


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


def test_resonance_x_uses_representative_x_when_present() -> None:
    resonance = Resonance(
        high_power_peaks=PeakGroup([Peak(x=10, y=4, prominence=1.0)]),
        low_power_peak=None,
        representative_x=13,
    )

    assert resonance.x == 13


def test_select_local_resonance_prefers_adjacent_low_power_candidate_with_stronger_high_power() -> (
    None
):
    high_only = Resonance(
        high_power_peaks=PeakGroup(
            [Peak(x=10, y=4, prominence=0.5), Peak(x=10, y=5, prominence=0.4)]
        ),
        low_power_peak=None,
    )
    adjacent_low = Resonance(
        high_power_peaks=PeakGroup(
            [Peak(x=11, y=4, prominence=0.9), Peak(x=11, y=5, prominence=0.8)]
        ),
        low_power_peak=Peak(x=11, y=3, prominence=0.3),
    )

    selected, rejected = _select_local_resonance([high_only, adjacent_low])

    assert selected is adjacent_low
    assert rejected == [high_only]


def test_select_resonances_refills_with_non_overlapping_candidate() -> None:
    config = EstimateResonatorFrequencyConfig(
        num_resonators=2,
        compose_resonances_conf=ComposeResonancesConfig(x_distance_max=25, x_backward_max=2),
        group_resonances_conf=GroupResonancesConfig(x_distance_max=25),
    )
    peak_groups = [
        PeakGroup([Peak(x=10, y=4, prominence=0.9)]),
        PeakGroup([Peak(x=12, y=4, prominence=0.8)]),
        PeakGroup([Peak(x=60, y=4, prominence=0.7)]),
    ]
    low_power_peaks: list[Peak] = []

    selected, rejected = _select_resonances(peak_groups, low_power_peaks, config)

    assert [resonance.x for resonance in selected] == [10, 60]
    assert [resonance.x for resonance in rejected] == [12]


def test_refine_high_power_only_resonance_x_sets_representative_x_from_stronger_upper_row_signal() -> (
    None
):
    resonance = Resonance(
        high_power_peaks=PeakGroup([Peak(x=2, y=2, prominence=1.0)]),
        low_power_peak=None,
    )
    zs = [
        [0.0, 0.0, 0.0, 0.0, 8.0],
        [0.0, 0.0, 0.0, 6.0, 0.0],
        [0.0, 0.0, 5.0, 0.0, 0.0],
    ]

    refined = _refine_high_power_only_resonance_x(
        resonance,
        zs,
        y_idx_high_min=0,
        x_distance_max=2,
    )

    assert refined.representative_x == 4
    assert refined.x == 4
    assert refined.complementary_peaks[-1] == Peak(x=4, y=0, prominence=8.0)


def test_select_diverse_resonances_rebalances_weak_right_edge_with_left_candidate() -> None:
    left_edge = Resonance(
        high_power_peaks=PeakGroup(
            [Peak(x=10, y=4, prominence=0.2), Peak(x=22, y=5, prominence=0.3)]
        ),
        low_power_peak=Peak(x=10, y=2, prominence=0.1),
    )
    middle_a = Resonance(
        high_power_peaks=PeakGroup([Peak(x=40, y=4, prominence=0.9)]),
        low_power_peak=Peak(x=40, y=3, prominence=0.4),
    )
    middle_b = Resonance(
        high_power_peaks=PeakGroup([Peak(x=60, y=4, prominence=0.9)]),
        low_power_peak=Peak(x=60, y=3, prominence=0.4),
    )
    middle_c = Resonance(
        high_power_peaks=PeakGroup([Peak(x=80, y=4, prominence=0.9)]),
        low_power_peak=Peak(x=80, y=3, prominence=0.4),
    )
    weak_right_edge = Resonance(
        high_power_peaks=PeakGroup([Peak(x=100, y=4, prominence=0.7)]),
        low_power_peak=Peak(x=100, y=3, prominence=0.4),
    )

    selected, rejected = _select_diverse_resonances(
        [left_edge, middle_a, middle_b, middle_c, weak_right_edge],
        num_resonators=4,
        x_distance_max=25,
    )

    assert [resonance.x for resonance in selected] == [10, 40, 60, 80]
    assert rejected == [weak_right_edge]


def test_needs_diverse_reselection_for_weak_non_adjacent_resonance() -> None:
    weak_non_adjacent = Resonance(
        high_power_peaks=PeakGroup([Peak(x=10, y=5, prominence=0.3)]),
        low_power_peak=Peak(x=20, y=2, prominence=0.2),
    )

    assert _needs_diverse_reselection([weak_non_adjacent])


def test_guess_sorted_slots_for_partial_mux_assigns_large_gap_missing_slot() -> None:
    xs = [float(i) for i in range(100)]

    slots, mode = guess_sorted_slots_for_partial_mux(xs, [10.0, 50.0, 60.0])

    assert slots == [0, 2, 3]
    assert mode == "slot1-missing-large-left-gap"
