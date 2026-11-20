"""Create a separate, synthetic SQLite database for offline dashboard testing."""

import argparse
from contextlib import closing
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sqlite3

from zever import initialise_database


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(__file__).with_name("demo_zever.db"))
    args = parser.parse_args(argv)
    if args.db.exists():
        print(f"Demo database already exists: {args.db} (not overwritten)")
        return 0

    args.db.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for age in range(89, -1, -1):
        day = date.today() - timedelta(days=age)
        if age % 11 == 3:  # demonstrate whole missing days
            continue
        for serial, capacity in (("DEMO-A", 3300), ("DEMO-B", 2400)):
            total = 0.0
            for minute in range(7 * 60, 19 * 60 + 1, 5):
                hour = minute / 60
                power = round(capacity * max(0, 1 - abs(hour - 12.5) / 5.5))
                total += power / 12000  # W * five minutes / (60 * 1000)
                if age % 6 == 0 and 12 * 60 <= minute < 13 * 60:
                    continue  # demonstrate a missing hour without inventing it
                stamp = datetime.combine(day, time()) + timedelta(minutes=minute)
                rows.append((stamp.isoformat(sep=" "), serial, power, round(total, 4), "Normal"))

    with closing(sqlite3.connect(args.db)) as conn, conn:
        initialise_database(conn)
        conn.executemany("INSERT INTO inverterData VALUES(?,?,?,?,?)", rows)
        conn.commit()
    print(f"Created {args.db} with {len(rows)} synthetic readings; never use for live collection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())