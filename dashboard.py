"""Private-LAN ZeverSolar dashboard: Python standard-library HTTP server."""

import argparse
from contextlib import closing
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from analytics import get_readings
from config import load_config
from zever import DB_PATH, initialise_database

STATIC = Path(__file__).with_name("static")
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/bootstrap.min.css": ("bootstrap.min.css", "text/css; charset=utf-8"),
    "/static/bootstrap.bundle.min.js": ("bootstrap.bundle.min.js", "text/javascript; charset=utf-8"),
}


def handler_for(db_path):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json")
                             else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)

        def json_reply(self, status, payload):
            self.reply(status, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):
            path = urlsplit(self.path)
            if path.path == "/api/readings":
                try:
                    with closing(sqlite3.connect(db_path, timeout=30)) as conn:
                        data = get_readings(conn, parse_qs(path.query))
                    self.json_reply(200, data)
                except ValueError as exc:
                    self.json_reply(400, {"error": str(exc)})
                except sqlite3.Error:
                    self.log_error("SQLite query failed")
                    self.json_reply(503, {"error": "Readings database unavailable"})
                return
            if path.path in FILES:
                name, content_type = FILES[path.path]
                self.reply(200, (STATIC / name).read_bytes(), content_type)
            else:
                self.json_reply(404, {"error": "Not found"})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="settings file (default: config.ini beside script)")
    parser.add_argument("--host", help="dashboard bind address (overrides config.ini)")
    parser.add_argument("--port", type=int, help="dashboard port (overrides config.ini)")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)
    try:
        settings = load_config(args.config)
        host = args.host or os.environ.get("ZEVER_WEB_HOST") or settings.get(
            "dashboard", "host", fallback="127.0.0.1").strip()
        port = args.port if args.port is not None else int(
            os.environ.get("ZEVER_WEB_PORT") or settings.get("dashboard", "port", fallback="8080"))
        if not host or not 1 <= port <= 65535:
            raise ValueError("Dashboard host must not be empty; port must be 1–65535")
    except ValueError as exc:
        parser.error(str(exc))
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(args.db, timeout=30)) as conn, conn:
        initialise_database(conn)
    with ThreadingHTTPServer((host, port), handler_for(args.db)) as server:
        print(f"ZeverSolar: http://{host}:{server.server_port} (private LAN only)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
