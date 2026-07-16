"""FileTypeId -> (detail repository, mapper).

To add a company, add ONE entry to REGISTRY (and its mapper module). The Voyage
writer and the runner never change (Open/Closed). get_processor is the stable core.
"""
from app.lookups import FileType
from app.db.repositories.gpa_file_detail_repository import GpaFileDetailRepository
from app.processing.voyage.gpa.mapper import map_row as gpa_map_row

REGISTRY = {
    FileType.GPA: (GpaFileDetailRepository, gpa_map_row),
}


def get_processor(file_type_id: int):
    if file_type_id not in REGISTRY:
        raise KeyError(f"No processor registered for FileTypeId {file_type_id!r}")
    return REGISTRY[file_type_id]


def has_processor(file_type_id: int) -> bool:
    return file_type_id in REGISTRY