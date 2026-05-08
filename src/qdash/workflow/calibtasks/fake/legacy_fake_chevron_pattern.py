"""Legacy alias for the renamed FakeChevronPattern task.

Mirror of :mod:`qdash.workflow.calibtasks.qubex.one_qubit_coarse.legacy_chevron_pattern`
on the fake backend. Kept so that historical fake-backend results with
``name = "ChevronPattern"`` remain filterable from the UI. New code should
use :class:`FakeCheckFineChevron` directly.
"""

from qdash.workflow.calibtasks.fake.fake_check_fine_chevron import FakeCheckFineChevron


class FakeChevronPattern(FakeCheckFineChevron):
    """Legacy alias for FakeCheckFineChevron — kept for UI filtering of historical results."""

    name: str = "ChevronPattern"
    # task_type must be re-declared so the AST parser in
    # task_file_service picks it up (inherited attributes are invisible to it).
    task_type: str = "qubit"
