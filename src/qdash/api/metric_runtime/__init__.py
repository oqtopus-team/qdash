"""Runtime for user-authored metric scripts.

Scripts import the public ``qdash_metrics`` API (:mod:`.sdk`) and run in a separate,
resource-bounded worker process (:mod:`.worker`) that the metric runner in agent-exec starts
for :mod:`.executor`. The worker has no database, credential or API access; it reads data
only through the line-delimited JSON data broker (:mod:`.broker`) that runs in the API
process and applies project scoping.

This package must stay import-light: the worker imports :mod:`.sdk`, :mod:`.policy` and
:mod:`.worker` only, never FastAPI, repositories or database models.
"""
