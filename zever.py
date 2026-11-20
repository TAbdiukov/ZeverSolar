"""Read a ZeverSolar inverter's HTTP /home.cgi endpoint into SQLite."""

import argparse
from contextlib import closing
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests
from config import load_config

DB_PATH = Path(os.environ.get("ZEVER_DB", Path(__file__).with_name("zeverData.db")))
LOG = logging.getLogger("zeversolar")


def initialise_database(conn):
    """Create missing structures without deleting an existing database."""
    conn.execute("""CREATE TABLE IF NOT EXISTS inverterData
                 (date text, SN text, PAC_W int, E_TODAY real, Status text)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zever_date ON inverterData(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zever_sn_date ON inverterData(SN, date)")
    conn.commit()


def correct_E_Today(kwh):
    """Work around ZeverSolar's '5.9' meaning '5.09' (but '5.90' is 5.90)."""
    value = str(kwh).strip()
    whole, dot, fraction = value.partition(".")
    if dot and len(fraction) == 1:
        value = f"{whole}.0{fraction}"
    result = float(value)
    if not (0 <= result < float("inf")):
        raise ValueError("Invalid daily energy reading")
    return result


def processZeverResponse(content):
    """Parse ZeverSolar's line-based response (up to five inverters)."""
    parts = [part.strip() for part in content.splitlines()]
    if len(parts) < 10:
        raise ValueError("Incomplete ZeverSolar response")

    count = int(parts[8])
    if not 0 <= count <= 5:
        raise ValueError("Invalid inverter count")
    if len(parts) < 9 + count * 4 + 1:
        raise ValueError("Truncated inverter or meter data")

    result = {
        "enable_wifi": parts[0],
        "Registry Key": parts[3],
        "Hardware Version": parts[4],
        "Software Version": parts[5],
        "Time": parts[6],
        "Zevercloud communication": "ok" if parts[7].startswith("OK") else "error",
    }
    if parts[1] in ("0", "3"):
        result["Serial Number"] = parts[2]
    else:
        result["Registry ID"] = parts[2]

    inverters = []
    index = 9
    for _ in range(count):
        serial, power, energy, status = parts[index:index + 4]
        watt = int(power)
        if watt < 0 or not serial:
            raise ValueError("Invalid inverter reading")
        inverters.append({
            "SN": serial,
            "PAC(W)": watt,
            "E_Today(KWh)": correct_E_Today(energy),
            "Status": status,
        })
        index += 4
    result["inverter"] = inverters

    meter = {"status": parts[index]}
    if meter["status"].startswith("OK"):
        if len(parts) < index + 5:
            raise ValueError("Truncated meter reading")
        meter.update(zip(("m_p", "m_in", "m_out", "m_meter"),
                         parts[index + 1:index + 5]))
    result["meter"] = meter
    return result


def inverter_url(host):
    """Accept an IP, hostname, base URL or full home.cgi URL."""
    raw = host if "://" in host else "http://" + host
    parsed = urlsplit(raw)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("Use an HTTP inverter host or URL")
    if parsed.path not in ("", "/", "/home.cgi") or parsed.query or parsed.fragment:
        raise ValueError("Expected the inverter host or /home.cgi")
    return f"{raw.rstrip('/').removesuffix('/home.cgi')}/home.cgi"


def collect_once(conn, session, url, verbose=False):
    response = session.get(url, cookies={"customer_l": "en_us"}, timeout=10)
    response.raise_for_status()
    result = processZeverResponse(response.text)
    timestamp = datetime.now().isoformat(sep=" ")
    rows = [
        (timestamp, inv["SN"], inv["PAC(W)"], inv["E_Today(KWh)"], inv["Status"])
        for inv in result["inverter"]
    ]
    if rows:
        conn.executemany("INSERT INTO inverterData VALUES (?,?,?,?,?)", rows)
        conn.commit()
    if verbose:
        LOG.info("Inverter readings: %s", result)
    return len(rows)


def start_collection(conn, url, interval=30, once=False, verbose=False):
    """Retry HTTP directly; no platform-dependent ping and no night-time busy loop."""
    failures = 0
    with requests.Session() as session:
        while True:
            try:
                count = collect_once(conn, session, url, verbose)
                failures = 0
                LOG.info("Stored %d inverter reading(s)", count)
                if once:
                    return
                delay = interval
            except (requests.RequestException, ValueError, IndexError) as exc:
                if once:
                    raise
                failures += 1
                delay = min(300, max(interval, 30) * 2 ** min(failures - 1, 4))
                LOG.warning("Inverter unavailable or response invalid: %s; retry in %ds", exc, delay)
            time.sleep(delay)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="optional inverter host (overrides config.ini)")
    parser.add_argument("--config", type=Path, help="settings file (default: config.ini beside script)")
    parser.add_argument("--initDB", action="store_true", help="create database if absent; never deletes data")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="SQLite database path")
    parser.add_argument("--once", action="store_true", help="read one sample and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))
    host = args.host or os.environ.get("ZEVER_HOST") or settings.get("inverter", "host", fallback="").strip()
    if not args.initDB and not host:
        parser.error("set [inverter] host in config.ini, set ZEVER_HOST or supply a host argument")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(args.db, timeout=30)) as conn, conn:
        initialise_database(conn)
        if not args.initDB:
            try:
                start_collection(conn, inverter_url(host), once=args.once,
                                 verbose=args.verbose)
            except KeyboardInterrupt:
                LOG.info("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
