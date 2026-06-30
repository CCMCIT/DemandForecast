"""Purpose: thin command-line entrypoint for the pipeline.

Parses arguments and delegates to the ingestion/processing runners. It holds NO
business logic (Single Responsibility) so the same flows can later be triggered
by a worker or API entrypoint without change. Two independent commands:

  ingest  --path <file> --type <FileType>   file on disk -> File_tbl + detail table
  process --file-id <id>                    a loaded file -> Voyage_tbl + VoyageDetails_tbl
"""
import argparse

from app.ingestion import runner as ingestion_runner
from app.processing import runner as processing_runner


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="forecast", description="Vessel demand forecast data pipeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Load a file into File_tbl and its company detail table")
    ingest.add_argument("--path", required=True, help="Path to the source file")
    ingest.add_argument("--type", required=True, dest="file_type", help="FileType, e.g. GPA")

    process = sub.add_parser(
        "process", help="Map a loaded file into Voyage_tbl and VoyageDetails_tbl"
    )
    process.add_argument("--file-id", required=True, type=int, dest="file_id", help="FileId to process")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        file_id = ingestion_runner.run(args.file_type, args.path)
        print(f"Ingested '{args.path}' as FileType={args.file_type}. FileId={file_id}")
    elif args.command == "process":
        count = processing_runner.process_file(args.file_id)
        print(f"Processed {count} detail row(s) for FileId={args.file_id}")


if __name__ == "__main__":
    main()
