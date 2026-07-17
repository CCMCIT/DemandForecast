"""Flask web entrypoint: a local click-UI over the same commands the CLI runs.

Sibling of app.entrypoints.cli. Holds NO business logic. Two kinds of route:

  * quick, read-only checks (health, import-status) run in-process and return JSON;
  * long-running commands (ingest, process, ...) are launched as a subprocess of
    the existing `run.py <command>` CLI, their printed output is streamed live to
    the browser, and a Stop button terminates that subprocess. Stopping reuses the
    CLI's own KeyboardInterrupt handling; a terminated job leaves the file at its
    last committed phase (per-phase transactions), so it stays resumable.

Intended for LOCAL use only (localhost): it has DB write access and no auth.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import wraps

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from app.config.settings import Env, DEFAULT_ENV, EXCEL_WATCH_FOLDER, connection_string
from app.db import session as db_session
from app.lookups import FileType
from app.ingestion import runner as ingestion_runner

app = Flask(__name__)
# Pick up template/CSS edits on a plain refresh, without restarting the server.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

# Project root (where run.py lives): src/app/entrypoints/web/app.py -> up 4.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# UI command -> CLI subcommand (run.py <name>). Only long-running commands stream.
_CLI_COMMANDS = {
    "ingest": "ingest",
    "ingest-folder": "ingest-folder",
    "process-pending": "process-pending",
    "process-next": "process-next",
    "process-gate-activity-pending": "process-gate-activity-pending",
}

# One local user -> at most one running job. A background thread reads the child's
# output into _lines; the page polls /api/logs for new lines. Guarded by _job_lock.
_job = None
_lines = []
_running = False
_job_lock = threading.Lock()


def _env() -> Env:
    """The environment chosen in the UI (falls back to the default)."""
    return Env(request.form.get("env", DEFAULT_ENV.value))


def _bind() -> Env:
    """Bind the DB engine to the UI's chosen environment, rebuilding the engine
    only when the environment actually changed — a single local user usually
    stays on one env, so this avoids recreating the connection pool per click."""
    env = _env()
    if db_session.active_env() != env:
        db_session.configure(env)
    return env


def api(fn):
    """Wrap a route that returns a dict: add ok=True, or turn any error into a
    clean ok=False message (no traceback) so the UI can just show it."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return jsonify({"ok": True, **fn(*args, **kwargs)})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)})
    return wrapper


@app.get("/")
def index():
    return render_template(
        "index.html",
        envs=[e.value for e in Env],
        default_env=DEFAULT_ENV.value,
        file_types=[t.name for t in FileType],
        watch_folder=EXCEL_WATCH_FOLDER,
    )


@app.post("/api/health")
def health():
    """Runtime readiness for the chosen environment: .env, DB, watch folder."""
    env = _env()
    checks = []

    try:
        connection_string(env)
        checks.append({"label": f".env has a connection string for '{env.value}'", "ok": True})
    except KeyError as exc:
        checks.append({"label": str(exc), "ok": False})

    try:
        _bind()
        db_session.ping()
        checks.append({"label": f"Database reachable ({env.value})", "ok": True})
    except Exception as exc:
        checks.append({"label": f"Database not reachable: {exc}", "ok": False})

    if os.path.isdir(EXCEL_WATCH_FOLDER):
        checks.append({"label": f"Watch folder exists ({EXCEL_WATCH_FOLDER})", "ok": True})
    else:
        checks.append({"label": f"Watch folder missing ({EXCEL_WATCH_FOLDER})", "ok": False})

    return jsonify({"ok": all(c["ok"] for c in checks), "checks": checks})


@app.post("/api/import-status")
@api
def import_status():
    _bind()
    summary = ingestion_runner.import_summary()
    return {
        "message": (
            f"{summary['imported']} of {summary['total']} file(s) imported "
            f"successfully ({summary['failed']} failed)."
        ),
        "data": summary,
    }


def _build_argv(command: str, env: Env):
    """Build the `python -u run.py <command> ...` argv for a UI command, plus a
    temp dir to clean up afterwards (None if the command uploads no file).

    `-u` keeps the child's stdout unbuffered so its lines stream live."""
    argv = [sys.executable, "-u", "run.py", _CLI_COMMANDS[command], "--env", env.value]
    tmp_dir = None

    if command == "ingest":
        upload = request.files.get("file")
        if upload is None or upload.filename == "":
            raise ValueError("No file selected.")
        # Save the upload under its own name so File_tbl.FileName is meaningful.
        tmp_dir = tempfile.mkdtemp(prefix="demandforecast_ui_")
        path = os.path.join(tmp_dir, secure_filename(upload.filename))
        upload.save(path)
        argv += ["--path", path, "--type", request.form["type"]]
    elif command == "ingest-folder":
        argv += ["--type", request.form["type"]]
        folder = request.form.get("folder", "").strip()
        if folder:
            argv += ["--folder", folder]
    elif command == "process-next":
        count = request.form.get("count", "").strip()
        if not count.isdigit() or int(count) < 1:
            raise ValueError("Enter how many files to process (a whole number ≥ 1).")
        argv += ["--count", count]

    return argv, tmp_dir


def _reader(proc, tmp_dir):
    """Background thread: drain the child's output into _lines as it arrives, then
    mark the job finished and clean up the temp dir."""
    global _running
    try:
        for line in iter(proc.stdout.readline, ""):
            with _job_lock:
                _lines.append(line.rstrip("\n"))
        proc.wait()
        tail = "--- finished ---" if proc.returncode == 0 else f"--- stopped (exit code {proc.returncode}) ---"
        with _job_lock:
            _lines.append(tail)
    finally:
        proc.stdout.close()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        with _job_lock:
            _running = False


@app.post("/api/start")
@api
def start():
    """Launch a long-running command as a subprocess and start capturing its
    output. The page then polls /api/logs. Rejects a second concurrent job."""
    global _job, _lines, _running
    command = request.form.get("command", "")
    if command not in _CLI_COMMANDS:
        raise ValueError(f"Unknown command: {command}")

    argv, tmp_dir = _build_argv(command, _env())  # may save the upload
    with _job_lock:
        if _running:
            return {"message": "A job is already running — stop it first.", "started": False}
        proc = subprocess.Popen(
            argv, cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        _job, _lines, _running = proc, [], True

    threading.Thread(target=_reader, args=(proc, tmp_dir), daemon=True).start()
    return {"started": True}


@app.get("/api/logs")
def logs():
    """New output lines since `offset`, plus whether the job is still running."""
    offset = request.args.get("offset", default=0, type=int)
    with _job_lock:
        return jsonify({"lines": _lines[offset:], "offset": len(_lines), "running": _running})


@app.post("/api/stop")
@api
def stop():
    """Terminate the running job, if any. Its open (uncommitted) DB transaction is
    rolled back by the server, leaving the file at its last committed phase."""
    with _job_lock:
        if not _running or _job is None:
            return {"message": "No job is running."}
        _job.terminate()
    return {"message": "Stop signal sent."}
