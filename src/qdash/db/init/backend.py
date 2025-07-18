from qdash.datamodel.backend import BackendModel
from qdash.db.init.initialize import initialize
from qdash.dbmodel.backend import BackendDocument


def init_backend_document(username: str, backend: str) -> None:
    """Initialize the backend document."""
    initialize()

    backend_model = BackendModel(
        name=backend,
        username=username,
    )

    BackendDocument.insert_backend(backend_model)
