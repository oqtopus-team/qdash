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
    # Resonator frequency estimation
    "ComposeResonancesConfig",
    "EstimateResonatorFrequencyConfig",
    "FindPeaksConfig",
    "GroupPeaksConfig",
    "GroupResonancesConfig",
    "Resonance",
    "create_marked_figure",
    "estimate_and_mark_figure",
    "estimate_local_bare_shift_boundary",
    "estimate_minimum_usable_power",
    "estimate_optimal_powers",
    "estimate_resonator_frequency",
    "estimate_resonator_frequency_from_figure",
    # Bare-shift boundary estimation
    "BareShiftBoundary",
    "BareShiftBoundaryEstimator",
    "BareShiftDebugOptions",
    "ConfigBareShiftBoundaryEstimator",
    "HighFrequencyStrengthBareShiftBoundaryEstimator",
    "create_bare_shift_boundary_estimator",
    # Qubit frequency estimation
    "EstimateQubitFrequencyConfig",
    "F01Result",
    "F12Result",
    "Peak",
    "QubitFrequencyResult",
    "QubitResponse",
    "create_qubit_marked_figure",
    "estimate_and_mark_qubit_figure",
    "estimate_qubit_frequency",
    "estimate_qubit_frequency_from_figure",
    # Representative-y strategies
    "FirstPointMeetingWidthFromTipStrategy",
    "HorizontalRunLengthEstimator",
    "PeakRepresentativeYStrategy",
    "WidthEstimator",
    # Remove false spike
    "RemoveFalseSpikeRange",
    "remove_false_spike",
    "remove_false_spike_from_figure",
]
