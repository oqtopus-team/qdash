"""Analysis modules for qubex calibration tasks."""

from qdash.analysis.spectroscopy.bare_shift import (
    BareShiftBoundary,
    BareShiftBoundaryEstimator,
    BareShiftDebugOptions,
    ConfigBareShiftBoundaryEstimator,
    HighFrequencyStrengthBareShiftBoundaryEstimator,
    create_bare_shift_boundary_estimator,
)
from qdash.analysis.spectroscopy.estimate_qubit_frequency import (
    EstimateQubitFrequencyConfig,
    F01Result,
    F12Result,
    Peak,
    QubitFrequencyResult,
    QubitResponse,
    estimate_qubit_frequency,
    estimate_qubit_frequency_from_figure,
)
from qdash.analysis.spectroscopy.estimate_qubit_frequency import (
    create_marked_figure as create_qubit_marked_figure,
)
from qdash.analysis.spectroscopy.estimate_qubit_frequency import (
    estimate_and_mark_figure as estimate_and_mark_qubit_figure,
)
from qdash.analysis.spectroscopy.estimate_resonator_frequency import (
    ComposeResonancesConfig,
    EstimateResonatorFrequencyConfig,
    FindPeaksConfig,
    GroupPeaksConfig,
    GroupResonancesConfig,
    Resonance,
    create_marked_figure,
    estimate_and_mark_figure,
    estimate_local_bare_shift_boundary,
    estimate_minimum_usable_power,
    estimate_optimal_powers,
    estimate_resonator_frequency,
    estimate_resonator_frequency_from_figure,
)
from qdash.analysis.spectroscopy.mux import NUM_RESONATORS, PEAK_POSITIONS
from qdash.analysis.spectroscopy.remove_false_spike import (
    RemoveFalseSpikeRange,
    remove_false_spike,
    remove_false_spike_from_figure,
)
from qdash.analysis.spectroscopy.representative_y import (
    FirstPointMeetingWidthFromTipStrategy,
    HorizontalRunLengthEstimator,
    PeakRepresentativeYStrategy,
    WidthEstimator,
)

__all__ = [
    # MUX layout
    "NUM_RESONATORS",
    "PEAK_POSITIONS",
    # Bare-shift boundary estimation
    "BareShiftBoundary",
    "BareShiftBoundaryEstimator",
    "BareShiftDebugOptions",
    # Resonator frequency estimation
    "ComposeResonancesConfig",
    "ConfigBareShiftBoundaryEstimator",
    # Qubit frequency estimation
    "EstimateQubitFrequencyConfig",
    "EstimateResonatorFrequencyConfig",
    "F01Result",
    "F12Result",
    "FindPeaksConfig",
    # Representative-y strategies
    "FirstPointMeetingWidthFromTipStrategy",
    "GroupPeaksConfig",
    "GroupResonancesConfig",
    "HighFrequencyStrengthBareShiftBoundaryEstimator",
    "HorizontalRunLengthEstimator",
    "Peak",
    "PeakRepresentativeYStrategy",
    "QubitFrequencyResult",
    "QubitResponse",
    # Remove false spike
    "RemoveFalseSpikeRange",
    "Resonance",
    "WidthEstimator",
    "create_bare_shift_boundary_estimator",
    "create_marked_figure",
    "create_qubit_marked_figure",
    "estimate_and_mark_figure",
    "estimate_and_mark_qubit_figure",
    "estimate_local_bare_shift_boundary",
    "estimate_minimum_usable_power",
    "estimate_optimal_powers",
    "estimate_qubit_frequency",
    "estimate_qubit_frequency_from_figure",
    "estimate_resonator_frequency",
    "estimate_resonator_frequency_from_figure",
    "remove_false_spike",
    "remove_false_spike_from_figure",
]
