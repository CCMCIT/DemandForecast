# Release Notes

## Version 0.1.0 — First Demo

First working version of DemandForecast. It takes a daily file all the way from
disk into the voyage tables, ready for forecasting later.

- **File ingestion** — read a daily GPA CSV file and load it into `File_tbl` and
  `GpaFileDetail_tbl`. One file at a time or a whole folder.
- **Voyage processing** — turn the ingested rows into `Voyage_tbl`,
  `VoyageDetails_tbl`, and the descriptive field maps. Reprocessing a file
  overwrites the old data while keeping history.
- **Command-line tool** — run ingestion and processing from the CLI against the
  dev, uat, or prod database, with each step tracked so an interrupted run can
  resume.
- **Faster processing** — voyage and field writes are sent to the database in
  batched calls instead of one call per row, which cuts the time to process a
  file on a remote database.
- **Web UI (demo)** — a simple Flask web page to run ingestion and processing
  from the browser instead of the command line.
