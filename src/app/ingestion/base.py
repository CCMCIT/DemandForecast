"""Base contracts for ingestion. Shared file: do not edit to add a company."""
from abc import ABC, abstractmethod


class BaseReader(ABC):
    """Reads a file on disk into raw rows. No DB access here."""

    @abstractmethod
    def read(self, path):
        """Return the file's rows. Disk -> rows only."""
        raise NotImplementedError


class BaseLoader(ABC):
    """Loads raw rows into the company's raw table via repositories. No raw SQL."""

    @abstractmethod
    def load(self, session, file_id, rows):
        """Insert rows for the given file. DB access through repositories only."""
        raise NotImplementedError
