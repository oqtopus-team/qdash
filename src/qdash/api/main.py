"""QDash API application entrypoint."""

from qdash.api.app_factory import create_app

app = create_app()
