"""Shared ingestion flow: file on disk -> raw company table.

One transaction per file: commit all, or rollback and set LoadStatus=FAILED.
Entrypoints (cli/worker/api) call this; the flow does not know how it was triggered.
"""
from app.ingestion.registry import get_handlers


def run(file_type, path):
    reader_cls, loader_cls = get_handlers(file_type)
    raise NotImplementedError("Ingestion flow not built yet.")
