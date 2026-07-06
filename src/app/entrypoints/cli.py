"""Purpose: thin command-line entrypoint for the pipeline.

Parses arguments and delegates to the ingestion/processing runners. It holds NO
business logic (Single Responsibility) so the same flows can later be triggered
by a worker or API entrypoint without change. Commands:

  ingest          --path <file> --type <FileType>   file on disk -> File_tbl + detail table
  ingest-folder   --type <FileType> [--folder <dir>] every file in a folder -> File_tbl + detail table
  process         --file-id <id>                    one loaded file -> Voyage_tbl + VoyageDetails_tbl
  process-pending                                   every file with LoadStatusId=2 -> Voyage(+Details)

The numbered listing shown by `--help` is generated from _COMMANDS below.
"""
import argparse
import sys

from app.config.settings import EXCEL_WATCH_FOLDER
from app.lookups import FileType
from app.ingestion import runner as ingestion_runner
from app.processing import runner as processing_runner


# name -> (one-line description, example). Drives both the numbered --help
# listing and each subcommand's own description. Keep in command order.
_COMMANDS = {
    "ingest": (
        "Load a file into File_tbl and its company detail table.",
        'python run.py ingest --path "C:/files/NineDayVessel.csv" --type GPA',
    ),
    "ingest-folder": (
        "Ingest every file in a folder (defaults to EXCEL_WATCH_FOLDER).",
        'python run.py ingest-folder --type GPA --folder "D:/incoming"',
    ),
    "process": (
        "Map one loaded file into Voyage_tbl and VoyageDetails_tbl.",
        "python run.py process --file-id 123",
    ),
    "process-pending": (
        "Process every file with LoadStatusId=2 (Inserted into FileDetail).",
        "python run.py process-pending",
    ),
    "import-status": (
        "Show how many files were imported successfully out of the total.",
        "python run.py import-status",
    ),
}


def _commands_help() -> str:
    """Numbered command list for the top-level --help, one blank row between."""
    lines = ["commands:", ""]
    for number, (name, (description, example)) in enumerate(_COMMANDS.items(), start=1):
        lines.append(f"  {number}. {name}")
        lines.append(f"       {description}")
        lines.append(f"       Eg: {example}")
        lines.append("")
    return "\n".join(lines)


def _add_command(sub, name: str):
    """Add a subparser hidden from the default list (we render our own), but
    still self-documenting via `run.py <name> --help`."""
    description, example = _COMMANDS[name]
    return sub.add_parser(
        name,
        help=argparse.SUPPRESS,
        description=f"{description}\n\nEg: {example}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="forecast",
        description="Vessel demand forecast data pipeline",
        epilog=_commands_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # metavar keeps the usage line tidy; help=SUPPRESS hides the
    # "positional arguments: <command>" block (we render commands in the epilog).
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="<command>", help=argparse.SUPPRESS
    )

    ingest = _add_command(sub, "ingest")
    ingest.add_argument("--path", required=True, help="Path to the source file")
    ingest.add_argument(
        "--type",
        required=True,
        dest="file_type",
        choices=[t.name for t in FileType],
        help="FileType, e.g. GPA",
    )

    ingest_folder = _add_command(sub, "ingest-folder")
    ingest_folder.add_argument(
        "--type",
        required=True,
        dest="file_type",
        choices=[t.name for t in FileType],
        help="FileType, e.g. GPA",
    )
    ingest_folder.add_argument(
        "--folder",
        default=None,
        help="Source directory. Defaults to EXCEL_WATCH_FOLDER from .env.",
    )

    process = _add_command(sub, "process")
    process.add_argument("--file-id", required=True, type=int, dest="file_id", help="FileId to process")

    _add_command(sub, "process-pending")
    _add_command(sub, "import-status")

    args = parser.parse_args(argv)

    # The full error (with traceback) is already stored in Process_Log_Error_tbl
    # by the runners. On the console we show only the main message, not the
    # Python traceback, and exit non-zero.
    try:
        run_command(args)
    except KeyboardInterrupt:
        # The runner already printed "user requested stop" and left the file at a
        # resumable status. Exit with the conventional SIGINT code, no traceback.
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


# Shown when a command starts. Falls back to a generic verb.
_START_MESSAGES = {
    "ingest": "Loading...",
    "ingest-folder": "Loading...",
    "process": "Processing...",
    "process-pending": "Processing...",
    "import-status": "Checking...",
}


def run_command(args) -> None:
    print(_START_MESSAGES.get(args.command, "Working..."))

    if args.command == "ingest":
        file_type_id = FileType[args.file_type]
        file_id = ingestion_runner.run(file_type_id, args.path)
        print(f"Ingested '{args.path}' as {args.file_type}. FileId={file_id}")
    elif args.command == "ingest-folder":
        file_type_id = FileType[args.file_type]
        folder = args.folder or EXCEL_WATCH_FOLDER
        result = ingestion_runner.run_folder(file_type_id, folder, progress=_print_folder_progress)
        print(
            f"Folder ingest complete ({folder}). "
            f"ingested={len(result['ingested'])} "
            f"skipped={len(result['skipped'])} "
            f"failed={len(result['failed'])}"
        )
    elif args.command == "process":
        count = processing_runner.process_file(args.file_id)
        print(f"Processed {count} detail row(s) for FileId={args.file_id}")
    elif args.command == "process-pending":
        result = processing_runner.process_pending(progress=_print_progress)
        print(
            f"Pending run complete. "
            f"processed={len(result['processed'])} "
            f"skipped={len(result['skipped'])} "
            f"failed={len(result['failed'])}"
        )
    elif args.command == "import-status":
        summary = ingestion_runner.import_summary()
        print(
            f"{summary['imported']} of {summary['total']} file(s) "
            f"imported successfully ({summary['failed']} failed)."
        )

    print("Completed.")


def _print_progress(event: str, **data) -> None:
    """Live per-file output for process-pending. Verbs padded so FileId lines up."""
    if event == "start":
        print(f"{data['total']} file(s) to process.")
    elif event == "processing":
        print(f"  {'processing':<10} FileId={data['file_id']}")
    elif event == "processed":
        print(f"  {'processed':<10} FileId={data['file_id']} ({data['count']} detail rows)")
    elif event == "skipped":
        print(f"  {'skipped':<10} FileId={data['file_id']} (no processor for its FileType)")
    elif event == "failed":
        print(f"  {'failed':<10} FileId={data['file_id']}: {data['error']}")


def _print_folder_progress(event: str, **data) -> None:
    """Live per-file output for ingest-folder. Verbs padded so names line up."""
    if event == "start":
        total = data["total"]
        print("No files found." if total == 0 else f"{total} file(s) found.")
    elif event == "ingesting":
        print(f"  {'ingesting':<10} {data['file_name']}")
    elif event == "ingested":
        print(f"  {'ingested':<10} {data['file_name']} -> FileId={data['file_id']}")
    elif event == "skipped":
        print(f"  {'skipped':<10} {data['file_name']} (already inserted)")
    elif event == "failed":
        print(f"  {'failed':<10} {data['file_name']}: {data['error']}")


if __name__ == "__main__":
    main()