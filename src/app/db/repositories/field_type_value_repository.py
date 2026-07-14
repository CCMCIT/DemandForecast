"""Repository for FieldTypeValue_tbl (the FieldType + FieldValue dimension)."""
from app.db.models.field_value import FieldValue
from app.db.models.field_type_value import FieldTypeValue


class FieldTypeValueRepository:
    def __init__(self, session):
        self.session = session

    def value_to_id(self, field_type_id: int) -> dict[str, int]:
        """Every value of one FieldType, as {text: FieldTypeValueId}.

        Loaded once per run and held by the caller, so resolving a value costs no
        DB hit per row -- the same pattern as ModeRepository/DirectionRepository.
        """
        rows = (
            self.session.query(FieldValue.FieldValue, FieldTypeValue.FieldTypeValueId)
            .join(FieldTypeValue, FieldTypeValue.FieldValueId == FieldValue.FieldValueId)
            .filter(FieldTypeValue.FieldTypeId == field_type_id)
            .all()
        )
        return {value: field_type_value_id for value, field_type_value_id in rows}
