from datetime import date
from urllib.parse import parse_qs
import sqlite3
import unittest

from analytics import get_readings, read_options
from zever import initialise_database


def query(conn, **kwargs):
    settings = {"from": ["2026-01-01"], "to": ["2026-01-03"],
                "granularity": ["daily"], "season": ["all"],
                "inverter": ["all"], "hour_from": ["0"], "hour_to": ["24"]}
    settings.update({key: [str(value)] for key, value in kwargs.items()})
    return get_readings(conn, settings)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        initialise_database(self.conn)
        rows = [
            ("2026-01-01 08:00:00", "A", 1000, .20, "Normal"),
            ("2026-01-01 08:02:00", "A", 1000, .30, "Normal"),
            ("2026-01-01 09:00:00", "A", 1000, .50, "Normal"),
            ("2026-01-01 09:02:00", "A", 1000, .60, "Normal"),
            ("2026-01-01 08:00:00", "B", 1000, .10, "Normal"),
            ("2026-01-01 08:02:00", "B", 1000, .20, "Normal"),
            ("2026-01-03 08:00:00", "A", 1000, .10, "Normal"),
            ("2026-03-02 09:00:00", "A", 1000, 2.00, "Normal"),
        ]
        self.conn.executemany("INSERT INTO inverterData VALUES(?,?,?,?,?)", rows)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_daily_meter_maximums_gaps_and_inverter_coverage(self):
        data = query(self.conn)
        self.assertEqual([p["kwh"] for p in data["periods"]], [.8, None, .1])
        self.assertEqual([p["status"] for p in data["periods"]], ["recorded", "missing", "partial"])
        self.assertEqual(data["summary"]["kwh"], .9)
        self.assertEqual(data["summary"]["missing"], 1)
        self.assertEqual(data["summary"]["partial"], 1)

    def test_single_inverter(self):
        data = query(self.conn, inverter="A")
        self.assertEqual([p["kwh"] for p in data["periods"]], [.6, None, .1])
        self.assertEqual(data["summary"]["latest_power"]["watts"], 1000)

    def test_hourly_energy_skips_long_gaps_but_keeps_zero_readings(self):
        data = query(self.conn, granularity="hourly", to="2026-01-01", hour_from=8, hour_to=10)
        self.assertEqual([p["kwh"] for p in data["periods"]], [.2, .1])
        data = query(self.conn, granularity="hourly", to="2026-01-01", hour_from=7, hour_to=10)
        self.assertIsNone(data["periods"][0]["kwh"])
        self.assertEqual(data["periods"][0]["status"], "missing")

    def test_filtered_day_is_based_on_observed_intervals_not_full_daily_maximum(self):
        data = query(self.conn, to="2026-01-01", hour_from=8, hour_to=9)
        self.assertEqual(data["periods"][0]["kwh"], .2)
        self.assertEqual(data["basis"], "short-interval estimate")

    def test_southern_season_and_annual(self):
        data = query(self.conn, season="autumn", to="2026-03-03")
        self.assertEqual(len(data["periods"]), 3)
        self.assertEqual(data["periods"][1]["kwh"], 2)
        data = query(self.conn, granularity="annual", to="2026-03-03", season="summer")
        self.assertEqual(len(data["periods"]), 1)
        self.assertEqual(data["periods"][0]["kwh"], .9)

    def test_weekly_buckets_start_monday_and_note_partial_days(self):
        data = query(self.conn, granularity="weekly")
        self.assertEqual(data["periods"][0]["start"], "2025-12-29")
        self.assertEqual(data["periods"][0]["recorded"], 3)
        self.assertEqual(data["periods"][0]["expected"], 6)

    def test_energy_crossing_hour_is_split_without_filling_gap(self):
        self.conn.executemany("INSERT INTO inverterData VALUES(?,?,?,?,?)", [
            ("2026-01-04 08:59:00", "A", 1000, 1.0, "Normal"),
            ("2026-01-04 09:01:00", "A", 1000, 1.2, "Normal"),
        ])
        data = query(self.conn, granularity="hourly", inverter="A",
                     **{"from": "2026-01-04", "to": "2026-01-04", "hour_from": 8, "hour_to": 10})
        self.assertEqual([period["kwh"] for period in data["periods"]], [.1, .1])

    def test_oversized_query_rejected_before_fetching_raw_samples(self):
        from unittest.mock import patch
        with patch("analytics.hourly_observed_energy", side_effect=AssertionError("read too much data")):
            with self.assertRaisesRegex(ValueError, "more than 800"):
                query(self.conn, granularity="hourly", to="2026-02-28")

    def test_invalid_query_and_injection_rejected(self):
        for settings in ({"from": "2026-03-02", "to": "2026-01-01"},
                         {"hour_from": 20, "hour_to": 7},
                         {"granularity": "nanosecond"},
                         {"inverter": "A' OR 1=1 --"},
                         {"from": "2026-02-30"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                query(self.conn, **settings)

    def test_too_many_buckets_rejected(self):
        with self.assertRaisesRegex(ValueError, "more than 800"):
            query(self.conn, granularity="hourly", to="2026-02-28")

    def test_no_data_still_returns_nulls(self):
        data = query(self.conn, to="2026-01-05", season="all")
        self.assertEqual(data["periods"][-1]["kwh"], None)
        self.assertEqual(data["summary"]["missing"], 3)
