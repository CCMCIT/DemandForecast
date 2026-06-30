"""Purpose: map a File's FileType to the pieces needed to process it.

FileType -> (detail repository, mapper). This is the single extension point for
processing: a new company adds ONE entry here plus its mapper module. The writer
and runner never change (Open/Closed). get_processor is the stable core.
"""
from app.db.repositories.gpa_file_detail_repository import GpaFileDetailRepository
from app.processing.gpa.mapper import map_row as gpa_map_row

REGISTRY = {
    "GPA": (GpaFileDetailRepository, gpa_map_row),
}


def get_processor(file_type: str):
    if file_type not in REGISTRY:
        raise KeyError(f"No processor registered for FileType {file_type!r}")
    return REGISTRY[file_type]