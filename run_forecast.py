"""Purpose: launcher for the forecast scripts, so they run without setting PYTHONPATH.

The forecast module needs TWO roots on sys.path:

  src/                 -> `app.config.settings`, `app.lookups` (shared with the
                          ingestion/processing side)
  src/app/forecast/    -> `db`, `forecast`, `pipelines` (the forecast layer's own
                          top-level packages; they have no __init__.py and are
                          resolved relative to this directory)

run.py covers the first for the ingestion CLI. This covers both, so a forecast
script can be launched from anywhere - CLI, PyCharm, a scheduled task - without
a working-directory convention or a PYTHONPATH entry in each run configuration.

Run from the project root with the virtualenv active:

    python run_forecast.py outgate-train --env dev --start 2023-01-01 \
        --end 2025-06-30 --modified-by <account>
    python run_forecast.py train --env dev --model-name <name> --target <feature> \
        --predictors <a> <b> --start 2023-01-01 --end 2025-06-30 --modified-by <account>
    python run_forecast.py outgate-score --env dev --model-id <id> --equip-length 20 \
        --train-start 2026-02-01 --train-end 2026-06-30 --modified-by <account>
    python run_forecast.py dow-train --env dev --modified-by <account>
    python run_forecast.py dow-score --env dev --model-id <id> --modified-by <account>

Everything after the command name is passed through to that script's own
argparse, so --help works per command:

    python run_forecast.py outgate-train --help
"""
import importlib
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
_FORECAST = os.path.join(_SRC, "app", "forecast")

for path in (_SRC, _FORECAST):
    if path not in sys.path:
        sys.path.insert(0, path)

# Command -> the module whose main(argv) it delegates to. Adding a script here
# is the only step needed to make it launchable.
_COMMANDS = {
    "outgate-train": "pipelines.outgate_train_run",
    "outgate-score": "pipelines.outgate_score_run",
    "train": "pipelines.train_run",
    "dow-train": "day_of_week_train_run",
    "dow-score": "day_of_week_score_run",
}


def _usage() -> str:
    lines = ["usage: python run_forecast.py <command> [options]", "", "commands:"]
    lines += [f"  {name:<15} {module}" for name, module in _COMMANDS.items()]
    lines += ["", "Run 'python run_forecast.py <command> --help' for a command's options."]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(_usage())
        raise SystemExit(0 if len(sys.argv) >= 2 else 2)

    command, argv = sys.argv[1], sys.argv[2:]
    if command not in _COMMANDS:
        print(f"Unknown command: {command}\n\n{_usage()}", file=sys.stderr)
        raise SystemExit(2)

    module = importlib.import_module(_COMMANDS[command])
    module.main(argv)


if __name__ == "__main__":
    main()
