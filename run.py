"""Purpose: project launcher so the CLI runs without setting PYTHONPATH.

Puts src/ on sys.path, then delegates to the CLI entrypoint. Run from the
project root with the virtualenv active:

    python run.py ingest --path <file> --type GPA
    python run.py process --file-id <id>
    python run.py process-pending
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from app.entrypoints.cli import main  # noqa: E402  (import after sys.path setup)

if __name__ == "__main__":
    main()
