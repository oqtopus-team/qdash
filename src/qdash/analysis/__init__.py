"""Standalone analysis utilities used by both the workflow and the API.

Code under :mod:`qdash.analysis` MUST NOT depend on
:mod:`qdash.workflow.engine` (or anything that imports it). This package is
shared between the `api` container — which does not ship the workflow engine
— and the workflow itself.
"""
