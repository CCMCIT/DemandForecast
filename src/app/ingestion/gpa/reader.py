"""GPA file reader: CSV on disk -> raw rows. No DB access, no type coercion."""
import csv

from app.ingestion.base import BaseReader


class GpaReader(BaseReader):
    def read(self, path) -> list[dict]:
        # utf-8-sig drops the BOM some exporters add to the first header.
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [self._normalise(row) for row in csv.DictReader(f)]

    @staticmethod
    def _normalise(row: dict) -> dict:
        # CSV headers like "FROM PORT" map to columns like FROM_PORT.
        return {
            (key or "").strip().replace(" ", "_"): (value.strip() if isinstance(value, str) else value)
            for key, value in row.items()
        }