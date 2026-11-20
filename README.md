# ZeverSolar · Raspberry Pi energy monitor

Modernised version of the original Python ZeverSolar HTTP collector. Collects from the inverter/gateway's **local HTTP `/home.cgi` endpoint**, writes to the **original SQLite `inverterData` table**, and serves a Bootstrap dashboard with hourly, daily, weekly, monthly and annual energy views.

**Assumptions:** Your device still exposes the same newline-delimited `home.cgi` response as the original project, and the Raspberry Pi's clock/timezone matches the installation's local time. The supplied parser has tests, but this project has **not yet been tested against your physical inverter**. This is designed for a **trusted home LAN only**, not the public internet. Seasons are **Southern Hemisphere** (summer Dec–Feb).

## Installation on Raspberry Pi OS

Requires Python **3.9+**, a working local connection to the inverter, and modest storage for the growing SQLite database. No Node.js, JavaScript build, cloud service or online dashboard assets are required.

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd ~
# Copy or unzip the delivered zeversolar_updated directory here:
mv zeversolar_updated zeversolar
cd ~/zeversolar
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Set the actual LAN IP address/hostname of your ZeverSolar gateway:

```bash
# This creates the database if it doesn't already exist; it NEVER erases readings.
.venv/bin/python zever.py --initDB
.venv/bin/python zever.py 192.168.1.50 --once --verbose
# Continuous data capture (every 30 seconds when reachable):
.venv/bin/python zever.py 192.168.1.50
```

In a **second terminal**, start the local dashboard:

```bash
cd ~/zeversolar
.venv/bin/python dashboard.py --host 0.0.0.0 --port 8080
```

On another device on the same network, browse to **`http://<pi-LAN-IP>:8080`**. For Pi-only access, omit `--host` and open `http://127.0.0.1:8080`. `0.0.0.0` listens on every Pi interface: only enable it on a trusted, firewalled home network. There is no user authentication or HTTPS.

### Start both automatically on boot (optional)

Two systemd **user** unit files are supplied in `systemd/`. They expect the project directory at `~/zeversolar` and a `.venv` made as above. Create `~/zeversolar/zever.env` (this file is gitignored):

```ini
ZEVER_HOST=192.168.1.50
# Optional: ZEVER_DB=/home/your-user/zeversolar/zeverData.db
ZEVER_WEB_HOST=0.0.0.0
ZEVER_WEB_PORT=8080
```

Then:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now zever-collector.service zever-dashboard.service
sudo loginctl enable-linger "$(whoami)"
# Diagnostics:
systemctl --user status zever-collector.service zever-dashboard.service
journalctl --user -u zever-collector.service -n 50
```

**Important:** Copy `zever.env` from your machine, not this README; adapt any file paths. Keep it private. The dashboard does not need the gateway address—it reads the SQLite file created by the collector.

## Dashboard filtering and data rules

| Filter | Behaviour |
| --- | --- |
| Resolution | Hourly, daily, weekly (Monday start), monthly, annual |
| Dates | Inclusive `From` and `To` dates. Resolution changes select a sensible default range; dates can then be changed |
| Inverter | All serial numbers combined, or one serial number |
| Season | All, summer, autumn, winter, spring (Southern Hemisphere) |
| Hours | `From` inclusive, `Until` exclusive; `00:00–24:00` means all day |

- **Full-day energy** is the maximum `E_TODAY` value seen each day per inverter, in kWh, as in the original project's totals plot. Weekly/monthly/annual reports sum available daily values; missing days aren't imputed. If the last daily reading came before sunset the total can be an **undercount**.
- **Hourly and time-of-day-filtered energy** use increases in `E_TODAY` between adjacent readings of the **same inverter on the same day**, only when at most **five minutes** apart. Small intervals crossing an hour boundary are divided proportionally. Missing hours are shown without values. Large gaps, midnight resets and meter decreases are **not estimated**. Consequently, an hourly sum may be lower than that day's meter maximum. This is intentional, not contradictory data.
- **Recorded/partial/missing** means whether the selected periods have an observation for every expected selected inverter-day (or inverter-hour for an hourly graph). **It does not mean** uninterrupted daytime coverage. During sunset/night, ZeverSolar may provide no observations and the hourly view will correctly show no measured values, rather than false zeroes.
- **Last recorded power** is the sum of the latest stored power sample for each selected inverter. The timestamp is displayed: **it is not guaranteed live**.
- At most **800 chart periods** and **10 years** of calendar data can be requested at once; use narrower date ranges for hourly/detail work. Data tables are scrollable.
- The Pi uses the timestamps from its **local system clock**; set the Pi's time zone accurately (e.g. `sudo timedatectl set-timezone Australia/Sydney` for Sydney).

## Database migration and backup

An old `zeverData.db` works **unchanged**. The collector and web server create missing tables and indexes using `CREATE IF NOT EXISTS`; unlike the original `--initDB`, this **never drops the table**. Before upgrading, stop your old collector and back up the database:

```bash
cp -p zeverData.db zeverData.db.backup
```

The index build on an existing multi-million-row database may take a little while on a Pi, so ensure adequate free disk space. Collection and web service can read/write simultaneously. For a different path set `ZEVER_DB` in **both** processes or pass `--db /path/to/zeverData.db` to both.

## Optional legacy plot

`plotZever.py --today`, `plotZever.py --from 2026-01-01 --to 2026-01-31` and `plotZever.py --totals` work on a machine with a display. Matplotlib is **optional** and not installed on the Pi by default:

```bash
.venv/bin/python -m pip install matplotlib
.venv/bin/python plotZever.py --today
```

The unfinished `zeverPlotly.py` Cloud prototype has been retired and the old embedded API key removed.

## Tests

From the project directory:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover inverter parsing, meter values, decimal correction, idempotent DB setup, valid HTTP URL formation, storing multiple inverter rows, date filtering, inverter selection, seasonal/weekly grouping, missing periods, the five-minute gap rule, API responses, and bundled Bootstrap files. A live-inverter end-to-end test must still be performed on your network.

## Dependencies and third-party credits

- `requests` for polling HTTP; everything else server-side is Python standard library.
- Bundled **Bootstrap 5.3.6** CSS and JavaScript from the MIT-licensed Bootstrap distribution. See `THIRD_PARTY_NOTICES.md`.
- No external asset URLs: the dashboard still renders if the Pi and browser have no internet access.
