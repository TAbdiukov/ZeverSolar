"""Settings and offline-demo regressions; these use portable Python APIs."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import date, timedelta
from io import StringIO
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import dashboard
import make_demo_db
import zever
from analytics import get_readings
from config import load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.config = self.folder / "home network.ini"
        self.database = self.folder / "live.db"
        self.config.write_text(
            "[inverter]\nhost = 192.168.1.20\n"
            "[dashboard]\nhost = 127.0.0.1\nport = 8123\n",
            encoding="utf-8")

    def collect_url(self, args, env=None):
        with patch.dict(os.environ, {"ZEVER_HOST": "", **(env or {})}), \
             patch("zever.start_collection") as collect:
            zever.main(["--config", str(self.config), "--db", str(self.database), *args])
        return collect.call_args.args[1]

    def test_configured_inverter_host_is_used_without_cli_argument(self):
        self.assertEqual(self.collect_url(["--once"]), "http://192.168.1.20/home.cgi")

    def test_environment_and_cli_override_configured_inverter_host(self):
        self.assertEqual(self.collect_url(["--once"], {"ZEVER_HOST": "pi.local"}),
                         "http://pi.local/home.cgi")
        self.assertEqual(self.collect_url(["pi2.local", "--once"], {"ZEVER_HOST": "pi.local"}),
                         "http://pi2.local/home.cgi")

    def test_init_db_does_not_need_inverter_host(self):
        self.config.write_text("[inverter]\nhost =\n", encoding="utf-8")
        zever.main(["--config", str(self.config), "--initDB", "--db", str(self.database)])
        self.assertTrue(self.database.exists())

    def test_empty_host_fails_with_helpful_message(self):
        self.config.write_text("[inverter]\nhost =\n", encoding="utf-8")
        with patch.dict(os.environ, {"ZEVER_HOST": ""}), redirect_stderr(StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                zever.main(["--config", str(self.config), "--once", "--db", str(self.database)])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("[inverter] host", output.getvalue())

    def test_missing_and_malformed_config_are_reported(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            load_config(self.folder / "missing.ini")
        self.config.write_text("this is not valid INI", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cannot read"):
            load_config(self.config)

    def dashboard_bind(self, args, env=None):
        with patch.dict(os.environ, {"ZEVER_WEB_HOST": "", "ZEVER_WEB_PORT": "",
                                          **(env or {})}), \
             patch("dashboard.ThreadingHTTPServer") as server, \
             redirect_stdout(StringIO()):
            dashboard.main(["--config", str(self.config), "--db", str(self.database), *args])
        return server.call_args.args[0]

    def test_dashboard_uses_configured_host_and_port(self):
        self.assertEqual(self.dashboard_bind([]), ("127.0.0.1", 8123))

    def test_dashboard_environment_and_cli_override_config(self):
        self.assertEqual(self.dashboard_bind([], {"ZEVER_WEB_HOST": "0.0.0.0",
                                                 "ZEVER_WEB_PORT": "9001"}), ("0.0.0.0", 9001))
        self.assertEqual(self.dashboard_bind(["--host", "localhost", "--port", "2222"],
                                             {"ZEVER_WEB_HOST": "0.0.0.0", "ZEVER_WEB_PORT": "9001"}),
                         ("localhost", 2222))

    def test_invalid_dashboard_port_is_rejected(self):
        self.config.write_text("[dashboard]\nhost=127.0.0.1\nport=not-a-number\n", encoding="utf-8")
        with patch.dict(os.environ, {"ZEVER_WEB_PORT": ""}), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                dashboard.main(["--config", str(self.config), "--db", str(self.database)])
        self.assertEqual(caught.exception.code, 2)


class OfflineDemoTests(unittest.TestCase):
    def test_demo_database_is_separate_and_reusable(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "demo_zever.db"
            with redirect_stdout(StringIO()):
                self.assertEqual(make_demo_db.main(["--db", str(database)]), 0)
            with closing(sqlite3.connect(database)) as conn:
                count = conn.execute("SELECT COUNT(*) FROM inverterData").fetchone()[0]
                serials = {row[0] for row in conn.execute("SELECT DISTINCT SN FROM inverterData")}
                first = str(date.today() - timedelta(days=29))
                last = str(date.today())
                result = get_readings(conn, {"from": [first], "to": [last]})
            self.assertGreater(count, 1000)
            self.assertEqual(serials, {"DEMO-A", "DEMO-B"})
            self.assertGreater(result["summary"]["with_data"], 0)
            self.assertGreater(result["summary"]["missing"], 0)
            with redirect_stdout(StringIO()):
                self.assertEqual(make_demo_db.main(["--db", str(database)]), 0)
            with closing(sqlite3.connect(database)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM inverterData").fetchone()[0], count)


if __name__ == "__main__":
    unittest.main()