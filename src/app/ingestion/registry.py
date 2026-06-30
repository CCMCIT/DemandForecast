"""FileType -> (reader, loader).

To add a company, add ONE entry to REGISTRY (and its reader/loader module).
The core (get_handlers) does not change.
"""
from app.ingestion.base import BaseReader, BaseLoader
from app.ingestion.gpa.reader import GpaReader
from app.ingestion.gpa.loader import GpaLoader

REGISTRY: dict[str, tuple[type[BaseReader], type[BaseLoader]]] = {
    "GPA": (GpaReader, GpaLoader),
}


def get_handlers(file_type: str) -> tuple[type[BaseReader], type[BaseLoader]]:
    if file_type not in REGISTRY:
        raise KeyError(f"No handlers registered for FileType {file_type!r}")
    return REGISTRY[file_type]