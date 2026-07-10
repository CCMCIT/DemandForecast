"""Purpose: stable lookup ids mirroring the DB's lookup tables.

The DB owns these tables (FileType_tbl, LoadStatus_tbl); their ids are mirrored
here as enums so the pipeline references them by name instead of magic numbers.
Keep in sync with the rows in those tables.
"""
from enum import IntEnum


class FileType(IntEnum):
    GPA = 1              # 'GPA 9-day vessel'
    NCSPA_IMPORTS = 2    # 'NCSPA Imports'
    NCSPA_EXPORTS = 3    # 'NCSPA Exports'


class LoadStatus(IntEnum):
    INSERTED_INTO_FILE = 1
    INSERTED_INTO_FILE_DETAIL = 2     # ingestion done: ready to process
    INSERTED_INTO_VOYAGE = 3
    INSERTED_INTO_VOYAGE_DETAIL = 4   # details done
    INSERTED_INTO_FIELD_MAP = 5       # field maps + all relevant tables done
    ERROR = 99


class VoyageStatus(IntEnum):
    TO_CALL = 1     # on the current report
    CALLED = 2      # fell off the report and was assessed as called
    CANCELED = 3    # fell off the report and was assessed as canceled


class FieldType(IntEnum):
    EQUIPMENT_TYPE = 1
    VESSEL = 2
    OCEAN_CARRIER = 3
    SERVICE = 4
    LOCATION = 5
    ORIGIN_PORT = 6
    DESTINATION_PORT = 7   # DB spells this 'Destination Port' (typo kept in the data)