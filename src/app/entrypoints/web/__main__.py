"""Start the local tester web UI:  python -m app.entrypoints.web

Binds to localhost only. It has DB write access and no auth — never expose it on
a network. Launched by start_ui.ps1 (which also sets PYTHONPATH=src).
"""
from app.entrypoints.web.app import app

if __name__ == "__main__":
    # threaded=True so /api/stop is handled while a command is streaming.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
