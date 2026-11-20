from contextlib import closing
import sqlite3
import unittest
from unittest.mock import Mock

from zever import (collect_once, correct_E_Today, initialise_database,
                   inverter_url, processZeverResponse)


def response_lines():
    return ["1", "3", "GW-1", "registry", "hw", "sw", "2026-11-20", "OK cloud", "2",
            "INV-1", "1100", "5.9", "Normal", "INV-2", "900", "5.90", "Normal",
            "OK meter", "123", "12", "34", "56"]


class ParserTests(unittest.TestCase):
    def test_parses_inverters_wifi_mode_and_meter(self):
        result = processZeverResponse("\r\n".join(response_lines()) + "\r\n")
        self.assertEqual(result["Serial Number"], "GW-1")
        self.assertEqual(result["inverter"][0]["E_Today(KWh)"], 5.09)
        self.assertEqual(result["inverter"][1]["E_Today(KWh)"], 5.90)
        self.assertEqual(result["meter"]["m_meter"], "56")
        self.assertEqual(result["meter"]["status"], "OK meter")

    def test_registry_id_and_no_meter(self):
        parts = response_lines()
        parts[1] = "1"
        parts[8] = "1"
        parts = parts[:13] + ["NO METER"]
        result = processZeverResponse("\n".join(parts))
        self.assertEqual(result["Registry ID"], "GW-1")
        self.assertEqual(result["meter"], {"status": "NO METER"})

    def test_bad_response_is_not_accepted(self):
        for response in ("", "1\n2", "\n".join(response_lines()[:12]),
                         "\n".join(response_lines()[:8] + ["99"] + response_lines()[9:])):
            with self.subTest(response=response[:20]), self.assertRaises(ValueError):
                processZeverResponse(response)

    def test_decimal_correction(self):
        self.assertEqual(correct_E_Today("0.1"), .01)
        self.assertEqual(correct_E_Today("6.90"), 6.9)
        self.assertEqual(correct_E_Today("6"), 6.0)
        for reading in ("abc", "-1.00", "nan", "inf"):
            with self.subTest(reading=reading), self.assertRaises(ValueError):
                correct_E_Today(reading)

    def test_url_normalisation_and_rejection(self):
        self.assertEqual(inverter_url("192.168.1.20"), "http://192.168.1.20/home.cgi")
        self.assertEqual(inverter_url("http://pi.local/home.cgi"), "http://pi.local/home.cgi")
        self.assertEqual(inverter_url("http://pi.local/"), "http://pi.local/home.cgi")
        with self.assertRaises(ValueError):
            inverter_url("https://some.host")
        with self.assertRaises(ValueError):
            inverter_url("192.168.1.20/admin")

    def test_initialisation_preserves_old_data(self):
        with closing(sqlite3.connect(":memory:")) as conn, conn:
            initialise_database(conn)
            conn.execute("INSERT INTO inverterData VALUES(?,?,?,?,?)", ("2020-01-01", "abc", 10, 1, "OK"))
            initialise_database(conn)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inverterData").fetchone()[0], 1)

    def test_collector_writes_one_transaction_for_all_inverters(self):
        with closing(sqlite3.connect(":memory:")) as conn, conn:
            initialise_database(conn)
            response = Mock()
            response.text = "\n".join(response_lines())
            session = Mock()
            session.get.return_value = response
            self.assertEqual(collect_once(conn, session, "http://test/home.cgi"), 2)
            session.get.assert_called_once_with("http://test/home.cgi",
                                                cookies={"customer_l": "en_us"}, timeout=10)
            self.assertEqual(conn.execute("SELECT SUM(PAC_W) FROM inverterData").fetchone()[0], 2000)
            self.assertEqual(conn.execute("SELECT E_TODAY FROM inverterData WHERE SN='INV-1'").fetchone()[0], 5.09)
