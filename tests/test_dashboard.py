from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from dashboard import handler_for
from zever import initialise_database


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        database = Path(self.directory.name) / "zeverData.db"
        with sqlite3.connect(database) as conn:
            initialise_database(conn)
            conn.execute("INSERT INTO inverterData VALUES(?,?,?,?,?)",
                         ("2026-01-01 11:00:00", "A", 100, .5, "Normal"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(database))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def test_html_and_local_bootstrap_files(self):
        for path, marker in (("/", b"ZeverSolar"),
                             ("/static/bootstrap.min.css", b"Bootstrap"),
                             ("/static/app.js", b"loadReadings")):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(marker, response.read())

    def test_api_includes_missing_days(self):
        with urlopen(self.url + "/api/readings?from=2026-01-01&to=2026-01-02") as response:
            data = json.load(response)
        self.assertEqual(data["periods"][0]["kwh"], .5)
        self.assertIsNone(data["periods"][1]["kwh"])
        self.assertEqual(data["summary"]["missing"], 1)

    def test_api_bad_parameters_return_400(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/readings?from=2026-01-12&to=2026-01-02")
        self.assertEqual(error.exception.code, 400)

    def test_unknown_route_is_404(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/static/../../zeverData.db")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
