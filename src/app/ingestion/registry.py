"""LoadTypeId -> (reader, loader).

To add a company, add ONE entry to REGISTRY (and its reader/loader module).
The core (get_handlers) does not change.
"""
from app.lookups import FileType
from app.ingestion.base import BaseReader, BaseLoader
from app.ingestion.gpa.reader import GpaReader
from app.ingestion.gpa.loader import GpaLoader

REGISTRY: dict[int, tuple[type[BaseReader], type[BaseLoader]]] = {
    FileType.GPA: (GpaReader, GpaLoader),
}


def get_handlers(file_type_id: int) -> tuple[type[BaseReader], type[BaseLoader]]:
    if file_type_id not in REGISTRY:
        raise KeyError(f"No handlers registered for LoadTypeId {file_type_id!r}")
    return REGISTRY[file_type_id]