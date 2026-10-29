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
