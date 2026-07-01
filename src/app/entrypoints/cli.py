"""Purpose: thin command-line entrypoint for the pipeline.

Parses arguments and delegates to the ingestion/processing runners. It holds NO
business logic (Single Responsibility) so the same flows can later be triggered
by a worker or API entrypoint without change. Commands:

  ingest          --path <file> --type <FileType>   file on disk -> File_tbl + detail table
  process         --file-id <id>                    one loaded file -> Voyage_tbl + VoyageDetails_tbl
  process-pending                                   every file with LoadStatusId=2 -> Voyage(+Details)
"""
import argparse

from app.lookups import FileType
from app.ingestion import runner as ingestion_runner
from app.processing import runner as processing_runner


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="forecast", description="Vessel demand forecast data pipeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Load a file into File_tbl and its company detail table")
    ingest.add_argument("--path", required=True, help="Path to the source file")
    ingest.add_argument(
        "--type",
        required=True,
        dest="file_type",
        choices=[t.name for t in FileType],
        help="FileType, e.g. GPA",
    )

    process = sub.add_parser(
        "process", help="Map one loaded file into Voyage_tbl and VoyageDetails_tbl"
    )
    process.add_argument("--file-id", required=True, type=int, dest="file_id", help="FileId to process")

    sub.add_parser(
        "process-pending",
        help="Process every file with LoadStatusId=2 (Inserted into FileDetail)",
    )

    args = parser.parse_args(argv)

    if args.command == "ingest":
        file_type_id = FileType[args.file_type]
        file_id = ingestion_runner.run(file_type_id, args.path)
        print(f"Ingested '{args.path}' as {args.file_type}. FileId={file_id}")
    elif args.command == "process":
        count = processing_runner.process_file(args.file_id)
        print(f"Processed {count} detail row(s) for FileId={args.file_id}")
    elif args.command == "process-pending":
        result = processing_runner.process_pending()
        print(
            f"Pending run complete. "
            f"processed={len(result['processed'])} "
            f"skipped={len(result['skipped'])} "
            f"failed={len(result['failed'])}"
        )
        for file_id, count in result["processed"]:
            print(f"  processed FileId={file_id} ({count} detail rows)")
        for file_id in result["skipped"]:
            print(f"  skipped   FileId={file_id} (no processor for its FileType)")
        for file_id, error in result["failed"]:
            print(f"  failed    FileId={file_id}: {error}")


if __name__ == "__main__":
    main()