"""Energy readings for the dashboard. No interpolation across outages."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import sqlite3

GRANULARITIES = ("hourly", "daily", "weekly", "monthly", "annual")
SEASONS = {"summer": {12, 1, 2}, "autumn": {3, 4, 5},
           "winter": {6, 7, 8}, "spring": {9, 10, 11}}
MAX_INTERVAL = timedelta(minutes=5)  # only allocate energy across short gaps
MAX_BUCKETS = 800


def day_range(first, last):
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def period_start(value, granularity):
    day = value.date() if isinstance(value, datetime) else value
    if granularity == "hourly":
        return value.replace(minute=0, second=0, microsecond=0)
    if granularity == "daily":
        return day
    if granularity == "weekly":
        return day - timedelta(days=day.weekday())
    if granularity == "monthly":
        return day.replace(day=1)
    return day.replace(month=1, day=1)


def period_label(start, granularity):
    if granularity == "hourly":
        return start.strftime("%d %b %H:%M")
    if granularity == "daily":
        return start.strftime("%d %b %Y")
    if granularity == "weekly":
        return "w/c " + start.strftime("%d %b %Y")
    if granularity == "monthly":
        return start.strftime("%b %Y")
    return str(start.year)


def read_options(params):
    """Validate an inclusive local-date range and bounded chart size."""
    granularity = params.get("granularity", ["daily"])[0]
    season = params.get("season", ["all"])[0]
    inverter = params.get("inverter", ["all"])[0].strip()
    if granularity not in GRANULARITIES or season not in (*SEASONS, "all"):
        raise ValueError("Invalid granularity or season")
    today = date.today()
    try:
        first = date.fromisoformat(params.get("from", [str(today - timedelta(days=29))])[0])
        last = date.fromisoformat(params.get("to", [str(today)])[0])
        start_hour = int(params.get("hour_from", ["0"])[0])
        end_hour = int(params.get("hour_to", ["24"])[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("Use YYYY-MM-DD dates and integer hours") from exc
    if first > last:
        raise ValueError("From date must not be after To date")
    if not (0 <= start_hour < end_hour <= 24):
        raise ValueError("Hours must be between 00:00 and 24:00, with start before end")
    if (last - first).days > 3660:
        raise ValueError("Maximum range is ten years; select a shorter period")
    if len(inverter) > 128:
        raise ValueError("Invalid inverter selection")
    return granularity, season, inverter, first, last, start_hour, end_hour


def daily_meter_readings(conn, first, last, inverter):
    """Daily meter maxima are reliable even with missing intermediate polls."""
    sql = ("SELECT substr(date, 1, 10), SN, MAX(E_TODAY) "
           "FROM inverterData WHERE date >= ? AND date < ? AND E_TODAY >= 0")
    args = [str(first), str(last + timedelta(days=1))]
    if inverter != "all":
        sql += " AND SN = ?"
        args.append(inverter)
    sql += " GROUP BY substr(date, 1, 10), SN"
    return {(date.fromisoformat(day), serial): float(kwh)
            for day, serial, kwh in conn.execute(sql, args) if kwh is not None}


def hourly_observed_energy(conn, first, last, inverter):
    """Use differences in the daily cumulative meter, only over gaps <= 5 min.

    Divide a short interval proportionally if it straddles an hour boundary.
    No interval across midnight is counted: the cumulative meter resets daily.
    """
    sql = ("SELECT date, SN, E_TODAY FROM inverterData "
           "WHERE date >= ? AND date < ? AND E_TODAY >= 0")
    args = [str(first), str(last + timedelta(days=1))]
    if inverter != "all":
        sql += " AND SN = ?"
        args.append(inverter)
    sql += " ORDER BY SN, date"

    observed = defaultdict(float)
    previous = {}
    for timestamp, serial, energy in conn.execute(sql, args):
        try:
            current = datetime.fromisoformat(timestamp)
            energy = float(energy)
        except (TypeError, ValueError):
            continue
        old = previous.get(serial)
        previous[serial] = (current, energy)
        if old is None:
            continue
        earlier, previous_energy = old
        gap = current - earlier
        if (current.date() != earlier.date() or not timedelta(0) < gap <= MAX_INTERVAL
                or energy < previous_energy):
            continue

        delta = energy - previous_energy
        total_seconds = gap.total_seconds()
        left = earlier
        while left < current:
            hour = left.replace(minute=0, second=0, microsecond=0)
            right = min(current, hour + timedelta(hours=1))
            observed[(hour, serial)] += delta * (right - left).total_seconds() / total_seconds
            left = right
    return observed


def latest_power(conn, selected):
    readings = []
    for serial in selected:
        row = conn.execute("SELECT date, PAC_W FROM inverterData WHERE SN=? "
                           "ORDER BY date DESC LIMIT 1", (serial,)).fetchone()
        if row:
            readings.append((row[0], int(row[1] or 0)))
    return {"watts": sum(w for _, w in readings) if readings else None,
            "last_seen": max((ts for ts, _ in readings), default=None)}


def get_readings(conn, params):
    granularity, season, inverter, first, last, hour_from, hour_to = read_options(params)
    serials = [row[0] for row in conn.execute("SELECT DISTINCT SN FROM inverterData ORDER BY SN")]
    if inverter != "all" and inverter not in serials:
        raise ValueError("Unknown inverter serial number")
    selected = serials if inverter == "all" else [inverter]
    filtered = hour_from != 0 or hour_to != 24
    # Fail fast: a multi-year hourly request must not scan millions of Pi rows
    # just to discover that the resulting chart is too large to display.
    possible = set()
    for day in day_range(first, last):
        if season != "all" and day.month not in SEASONS[season]:
            continue
        if granularity == "hourly":
            possible.update(datetime.combine(day, time(hour))
                            for hour in range(hour_from, hour_to))
        else:
            possible.add(period_start(day, granularity))
        if len(possible) > MAX_BUCKETS:
            raise ValueError(f"Range contains more than {MAX_BUCKETS} chart periods; narrow the dates")
    # Whole-day energy comes from the meter. For hourly/filtered reports,
    # use only reliable short-interval meter differences.
    data = (hourly_observed_energy(conn, first, last, inverter)
            if granularity == "hourly" or filtered
            else daily_meter_readings(conn, first, last, inverter))

    keys = defaultdict(set)  # expected calendar days/hours per period
    values = defaultdict(float)
    observed = defaultdict(set)  # (day-or-hour, inverter) with a valid reading
    for day in day_range(first, last):
        if season != "all" and day.month not in SEASONS[season]:
            continue
        if granularity == "hourly":
            for hour in range(hour_from, hour_to):
                current = datetime.combine(day, time(hour))
                key = period_start(current, granularity)
                keys[key].add(current)
                for serial in selected:
                    pair = (current, serial)
                    if pair in data:
                        values[key] += data[pair]
                        observed[key].add(pair)
        else:
            key = period_start(day, granularity)
            keys[key].add(day)
            for serial in selected:
                if filtered:
                    # Sum sampled hourly energy. Never interpolate an outage.
                    present = False
                    amount = 0.0
                    for hour in range(hour_from, hour_to):
                        pair = (datetime.combine(day, time(hour)), serial)
                        if pair in data:
                            amount += data[pair]
                            present = True
                    if present:
                        values[key] += amount
                        observed[key].add((day, serial))
                else:
                    pair = (day, serial)
                    if pair in data:
                        values[key] += data[pair]
                        observed[key].add(pair)

    if len(keys) > MAX_BUCKETS:
        raise ValueError(f"Range contains more than {MAX_BUCKETS} chart periods; narrow the dates")

    periods = []
    for key in sorted(keys):
        total_expected = len(keys[key]) * len(selected)
        n_observed = len(observed[key])
        value = round(values[key], 4) if n_observed else None
        periods.append({
            "start": key.isoformat(),
            "label": period_label(key, granularity),
            "kwh": value,
            "recorded": n_observed,
            "expected": total_expected,
            "status": ("missing" if n_observed == 0 else
                       "recorded" if n_observed == total_expected else "partial"),
        })
    nonempty = [period for period in periods if period["kwh"] is not None]
    return {
        "granularity": granularity,
        "basis": ("short-interval estimate" if granularity == "hourly" or filtered
                  else "daily meter maxima"),
        "season": season,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "serials": serials,
        "selected": selected,
        "from": str(first), "to": str(last),
        "periods": periods,
        "summary": {
            "kwh": round(sum(period["kwh"] for period in nonempty), 3),
            "with_data": len(nonempty),
            "missing": len(periods) - len(nonempty),
            "partial": sum(period["status"] == "partial" for period in periods),
            "total": len(periods),
            "latest_power": latest_power(conn, selected),
        },
    }
