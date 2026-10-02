class IngestionClientError(RuntimeError):
    """Safe external-ingestion error that may be persisted in a run summary."""


class IngestionResponseError(IngestionClientError):
    """An external response violated the application ingestion contract."""
