import numpy as np
import pytest

from qdash.analysis.capture_delay import (
    QUEL3_RESOLUTION_NS,
    Waveform,
    analyze_waveform,
    analyze_waveforms,
    finalize_delay,
    select_delay,
    split_total_delay,
    total_delay_ns,
)

SAMPLING_NS = 8.0
SAMPLES = 192
DURATION_NS = 1024.0
CENTER_NS = SAMPLES * SAMPLING_NS / 2


def _capture_at(
    total_ns: float,
    *,
    arrival_ns: float,
    target: str = "Q00",
    sampling_ns: float = SAMPLING_NS,
    samples: int = SAMPLES,
) -> Waveform:
    """Return a noisy rectangular pulse arriving ``arrival_ns`` after the trigger."""
    rng = np.random.default_rng(round(total_ns * 10))
    time = np.arange(samples) * sampling_ns
    start = arrival_ns - total_ns
    envelope = 0.5 * (np.tanh((time - start) / 6) - np.tanh((time - start - DURATION_NS) / 6))
    noise = rng.normal(size=samples) + 1j * rng.normal(size=samples)
    iq = envelope * (0.3 + 0.4j) + 0.005 * noise
    return Waveform(0, target, total_ns, time, iq, DURATION_NS)


def _capture(delay: int, word: int, *, arrival_ns: float, target: str = "Q00") -> Waveform:
    return _capture_at(total_delay_ns(delay, word), arrival_ns=arrival_ns, target=target)


def _calibrate(arrival_ns: float):
    targets = ("Q00", "Q01")
    coarse = analyze_waveforms(
        [_capture(d, 0, arrival_ns=arrival_ns, target=t) for d in range(19) for t in targets]
    )
    coarse_selection = select_delay(coarse, mux=0, center=CENTER_NS)
    assert coarse_selection.selected_total_ns is not None
    delay, _ = split_total_delay(coarse_selection.selected_total_ns)
    fine = analyze_waveforms(
        [
            _capture(delay, w, arrival_ns=arrival_ns, target=t)
            for w in (0, 4, 8, 12)
            for t in targets
        ]
    )
    fine_selection = select_delay(fine, mux=0, center=CENTER_NS)
    assert fine_selection.selected_total_ns is not None
    verification = analyze_waveforms(
        [
            _capture_at(fine_selection.selected_total_ns, arrival_ns=arrival_ns, target=t)
            for t in targets
        ]
    )
    return finalize_delay(verification, fine_selection, center=CENTER_NS)


def test_split_total_delay_uses_block_and_word_units():
    assert split_total_delay(total_delay_ns(9, 4)) == (9, 4)
    assert split_total_delay(1184.0) == (9, 4)


def test_analyze_waveform_detects_both_edges():
    result = analyze_waveform(_capture(9, 0, arrival_ns=1400.0), snr_threshold=5.0, smoothing=5)

    assert result.success
    assert result.edge_kind == "both"
    assert result.rise_ns == pytest.approx(1400.0 - 9 * 128, abs=2)
    assert result.fall_ns == pytest.approx(1400.0 - 9 * 128 + DURATION_NS, abs=2)


def test_analyze_waveform_reports_flat_capture():
    result = analyze_waveform(_capture(0, 0, arrival_ns=5000.0), snr_threshold=5.0, smoothing=5)

    assert not result.success
    assert result.reason == "low_contrast"


@pytest.mark.parametrize(
    ("arrival_ns", "expected"),
    [(1400.0, (9, 0)), (1430.0, (9, 4))],
)
def test_pipeline_centers_pulse_on_32ns_grid(arrival_ns, expected):
    final = _calibrate(arrival_ns)

    assert final.reason == "ready"
    assert final.final_total_ns is not None
    assert split_total_delay(final.final_total_ns) == expected
    assert final.predicted_pre_margin_ns is not None
    assert final.predicted_pre_margin_ns >= 32
    assert final.predicted_post_margin_ns is not None
    assert final.predicted_post_margin_ns >= 32
    assert final.predicted_midpoint_ns == pytest.approx(CENTER_NS, abs=16)


def test_select_delay_requires_two_delays_per_target():
    single = analyze_waveforms([_capture(9, 0, arrival_ns=1400.0)])

    selection = select_delay(single, mux=0, center=CENTER_NS)

    assert selection.selected_total_ns is None
    assert selection.reason == "insufficient_support"


def test_select_delay_reports_pulse_longer_than_window():
    time = np.arange(SAMPLES) * SAMPLING_NS
    waveforms = [
        Waveform(0, "Q00", d * 128.0, time, np.full(SAMPLES, 0.5 + 0j), 4096.0) for d in range(3)
    ]

    selection = select_delay(analyze_waveforms(waveforms), mux=0, center=CENTER_NS)

    assert selection.selected_total_ns is None


def test_quel3_pipeline_selects_on_the_readout_sampling_grid():
    arrival_ns, sampling_ns, samples = 1430.0, 0.8, 1920
    center = samples * sampling_ns / 2

    def capture(total_ns: float) -> Waveform:
        return _capture_at(
            total_ns, arrival_ns=arrival_ns, sampling_ns=sampling_ns, samples=samples
        )

    coarse = analyze_waveforms([capture(float(total)) for total in range(0, 2432, 128)])
    selection = select_delay(coarse, mux=0, center=center, resolution_ns=QUEL3_RESOLUTION_NS)
    assert selection.selected_total_ns is not None
    verification = analyze_waveforms([capture(selection.selected_total_ns)])
    final = finalize_delay(
        verification, selection, center=center, resolution_ns=QUEL3_RESOLUTION_NS
    )

    assert final.reason == "ready"
    assert final.final_total_ns is not None
    steps = final.final_total_ns / QUEL3_RESOLUTION_NS
    assert steps == pytest.approx(round(steps), abs=1e-6)
    # The pulse midpoint lands on the window center within one grid step.
    midpoint = arrival_ns - final.final_total_ns + DURATION_NS / 2
    assert midpoint == pytest.approx(center, abs=QUEL3_RESOLUTION_NS)


def test_long_pulse_in_narrow_1152ns_quel1_window_calibrates_cleanly():
    """A 1024 ns pulse in a 144-sample (1152 ns) window leaves only ~11% baseline."""
    samples = 144
    center = samples * SAMPLING_NS / 2
    arrival_ns = 1165.0  # centered near delay=8, word=12 (1120 ns)

    def capture(delay: int, word: int) -> Waveform:
        return _capture_at(
            total_delay_ns(delay, word),
            arrival_ns=arrival_ns,
            target="Q48",
            samples=samples,
        )

    coarse = analyze_waveforms([capture(d, 0) for d in range(19)])
    coarse_selection = select_delay(coarse, mux=0, center=center)
    assert coarse_selection.selected_total_ns is not None
    delay, _ = split_total_delay(coarse_selection.selected_total_ns)

    fine = analyze_waveforms([capture(delay, w) for w in (0, 4, 8, 12)])
    fine_selection = select_delay(fine, mux=0, center=center)
    assert fine_selection.selected_total_ns is not None

    verification = analyze_waveforms(
        [
            _capture_at(
                fine_selection.selected_total_ns,
                arrival_ns=arrival_ns,
                target="Q48",
                samples=samples,
            )
        ]
    )
    final = finalize_delay(verification, fine_selection, center=center)

    assert final.reason == "ready"
    assert final.final_total_ns is not None
    assert final.predicted_pre_margin_ns is not None
    assert final.predicted_pre_margin_ns >= 32
    assert final.predicted_post_margin_ns is not None
    assert final.predicted_post_margin_ns >= 32


def test_select_delay_uses_observed_duration_when_ringdown_broadens_pulse():
    """Observed rise-to-fall width avoids picking a delay that clips a broadened fall."""
    samples = 144
    center = samples * SAMPLING_NS / 2
    arrival_ns = 1165.0
    effective_duration_ns = 1044.0  # nominal 1024 ns + ~20 ns ring-down

    def broadened(delay: int, word: int) -> Waveform:
        total = total_delay_ns(delay, word)
        rng = np.random.default_rng(round(total * 10))
        time = np.arange(samples) * SAMPLING_NS
        start = arrival_ns - total
        envelope = 0.5 * (
            np.tanh((time - start) / 6) - np.tanh((time - start - effective_duration_ns) / 6)
        )
        noise = rng.normal(size=samples) + 1j * rng.normal(size=samples)
        return Waveform(0, "Q48", total, time, envelope * (0.2 + 0j) + 0.002 * noise, DURATION_NS)

    fine = analyze_waveforms([broadened(8, w) for w in (0, 4, 8, 12)])
    selection = select_delay(fine, mux=0, center=center)

    assert selection.selected_total_ns == total_delay_ns(8, 12)
    verification = analyze_waveforms([broadened(8, 12)])
    final = finalize_delay(verification, selection, center=center)
    assert final.reason == "ready"
    assert final.final_total_ns == total_delay_ns(8, 12)


def test_analyze_waveform_handles_phase_rotation_during_pulse():
    """Dispersive phase rotation across the pulse must not reject valid amplitude edges."""
    rng = np.random.default_rng(7)
    time = np.arange(SAMPLES) * SAMPLING_NS
    start = 1400.0 - total_delay_ns(9, 0)
    envelope = 0.5 * (np.tanh((time - start) / 6) - np.tanh((time - start - DURATION_NS) / 6))
    # Rotate complex phase by 2*pi across the pulse (e.g. off-resonant filter dispersion).
    phase = 2 * np.pi * (time - start) / DURATION_NS
    noise = rng.normal(size=SAMPLES) + 1j * rng.normal(size=SAMPLES)
    iq = envelope * 0.3 * np.exp(1j * phase) + 0.005 * noise
    wf = Waveform(0, "Q48", total_delay_ns(9, 0), time, iq, DURATION_NS)

    result = analyze_waveform(wf, snr_threshold=5.0, smoothing=5)

    assert result.success
    assert result.edge_kind == "both"
    assert result.rise_ns == pytest.approx(start, abs=2)
    assert result.fall_ns == pytest.approx(start + DURATION_NS, abs=2)


def test_analyze_waveform_fits_falling_edge_with_slow_ringdown_near_window_end():
    """Slow ring-down pushing the 50% crossing to sample n-4 must still fit fall_ns."""
    samples = 144
    time = np.arange(samples) * SAMPLING_NS
    # Rising edge at 45 ns; falling edge begins at 1060 ns with an exponential
    # ring-down tail so the smoothed 50% crossing sits around sample 140 (n - 4).
    amp = np.where(time < 45.0, 0.002, 0.20)
    tail = time >= 1060.0
    amp = np.where(tail, 0.20 * np.exp(-(time - 1060.0) / 70.0), amp)
    wf = Waveform(12, "Q48", total_delay_ns(8, 12), time, amp.astype(complex), DURATION_NS)

    result = analyze_waveform(wf, snr_threshold=5.0, smoothing=5)

    assert result.success
    assert result.edge_kind == "both"
    assert result.rise_ns is not None
    assert result.fall_ns is not None
    assert result.time_stop_ns - result.fall_ns >= 32.0
