"""Optional desktop plots from the same SQLite database as the web dashboard."""

import argparse
from datetime import date, datetime, timedelta
import sqlite3

from zever import DB_PATH


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--from", dest="start", help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--to", dest="end", help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--totals", action="store_true", help="daily generation instead of sampled W")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args(argv)
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        parser.error("Matplotlib is optional; install it with 'pip install matplotlib'")
    if args.today:
        first = last = date.today()
    else:
        first = date.fromisoformat(args.start) if args.start else date.today() - timedelta(days=6)
        last = date.fromisoformat(args.end) if args.end else date.today()
    if first > last:
        parser.error("--from must be on or before --to")

    with sqlite3.connect(args.db) as conn:
        if args.totals:
            rows = conn.execute(
                "SELECT substr(date,1,10), SN, MAX(E_TODAY) FROM inverterData "
                "WHERE date >= ? AND date < ? GROUP BY substr(date,1,10), SN ORDER BY date",
                (str(first), str(last + timedelta(days=1))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, SN, PAC_W FROM inverterData "
                "WHERE date >= ? AND date < ? ORDER BY date",
                (str(first), str(last + timedelta(days=1))),
            ).fetchall()
    if not rows:
        print("No readings in this date range")
        return
    grouped = {}
    for timestamp, serial, reading in rows:
        grouped.setdefault(serial, [[], []])
        grouped[serial][0].append(date.fromisoformat(timestamp) if args.totals
                                  else datetime.fromisoformat(timestamp))
        grouped[serial][1].append(reading)
    figure, ax = plt.subplots()
    for serial, (dates, readings) in grouped.items():
        ax.plot(dates, readings, label=serial)
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.set_ylabel("Daily generation (kWh)" if args.totals else "AC power (W)")
    ax.set_title(f"ZeverSolar: {first} to {last}")
    ax.legend()
    figure.autofmt_xdate()
    plt.show()


if __name__ == "__main__":
    main()
