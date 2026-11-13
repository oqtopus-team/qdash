"""Calibration tasks of the qibocal backend.

These tasks run upstream Qibocal protocols, with Qibocal's own acquisition, fit, and
report, on a Qibolab emulator through ``QibocalBackend``. QDash schedules the run, records
history, figures, and raw data, and keeps every output measurement-only.
"""

from qdash.workflow.calibtasks.qibocal.base import QibocalTask
from qdash.workflow.calibtasks.qibocal.rabi_amplitude import QibocalRabiAmplitude

__all__ = [
    "QibocalRabiAmplitude",
    "QibocalTask",
]
