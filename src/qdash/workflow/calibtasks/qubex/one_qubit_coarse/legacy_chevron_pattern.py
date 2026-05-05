"""Legacy alias for the renamed ChevronPattern task.

The task itself was renamed to CheckFineChevron for naming consistency with
CheckCoarseChevron. This file preserves the old class name so:

1. The UI task selector continues to expose ``ChevronPattern`` as a filterable
   option, allowing users to inspect historical task_result_history records
   (which have ``name = "ChevronPattern"``).
2. Any old DB / config reference to ``ChevronPattern`` still resolves via
   ``BaseTask.registry``.

New workflows should reference CheckFineChevron directly. This class is NOT
listed in ``config/backend.yaml`` ``qubex.tasks``, so the UI marks it as
``enabled=False`` and it won't be picked up by default task lists.
"""

from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_fine_chevron import (
    CheckFineChevron,
)


class ChevronPattern(CheckFineChevron):
    """Legacy alias for CheckFineChevron — kept for UI filtering of historical results."""

    name: str = "ChevronPattern"
    # task_type must be re-declared in the class body so the API's AST parser
    # (task_file_service._extract_task_info_from_file) sees it; inherited
    # attributes are invisible to the parser and the UI filters tasks by it.
    task_type: str = "qubit"
