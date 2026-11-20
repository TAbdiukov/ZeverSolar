"""Private-LAN ZeverSolar dashboard: Python standard-library HTTP server."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from analytics import get_readings
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
                    with sqlite3.connect(db_path, timeout=30) as conn:
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
    parser.add_argument("--host", default=os.environ.get("ZEVER_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ZEVER_WEB_PORT", "8080")))
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db, timeout=30) as conn:
        initialise_database(conn)
    with ThreadingHTTPServer((args.host, args.port), handler_for(args.db)) as server:
        print(f"ZeverSolar: http://{args.host}:{server.server_port} (private LAN only)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
