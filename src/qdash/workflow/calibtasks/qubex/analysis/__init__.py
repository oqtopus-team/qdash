"""Compatibility shim — analysis modules now live in :mod:`qdash.analysis.spectroscopy`.

The actual implementation was moved out of the workflow package so the API
container (which does not ship :mod:`qdash.workflow.engine`) can use the same
analysis code. New code should import from :mod:`qdash.analysis.spectroscopy`
directly; this re-export only exists to keep existing workflow imports
working.
"""

from qdash.analysis.spectroscopy import *  # noqa: F403
from qdash.analysis.spectroscopy import __all__  # noqa: F401
