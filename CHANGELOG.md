# Changelog

All dates use the YYYY-MM-DD format.

## 1.1.0 — 2026-11-20

### Added
- `config.ini` stores the ZeverSolar inverter IP/hostname and dashboard listen address/port.
- `--config` on both `zever.py` and `dashboard.py` for using an alternative settings file.
- Offline Windows test mode: `windows-demo.bat` creates a virtual environment, installs dependencies, generates `demo_zever.db` and runs the Bootstrap dashboard locally.
- `make_demo_db.py` produces synthetic readings with clearly visible missing periods, without touching live data.
- Automated tests for configuration values, precedence, errors and the demo database.
- Windows testing and migration instructions in the README.

### Changed
- Collector now reads its host from `[inverter] host` when no command-line host or `ZEVER_HOST` override is supplied.
- Dashboard now reads `[dashboard] host` and `port` by default; explicit CLI flags and the existing environment variables take precedence.
- Raspberry Pi systemd services no longer require a separate `zever.env` file; they use the same `config.ini` as interactive runs.
- Database connections used by the collector/dashboard startup and demo generator are now explicitly closed, allowing clean file release on Windows.

### Preserved
- Legacy positional inverter host and `ZEVER_*` environment variable overrides still work.
- The SQLite schema, existing readings, filters and offline Bootstrap interface are unchanged.

## 1.0.0 — 2026-11-20

Initial Raspberry Pi modernisation of the seven-year-old project: corrected HTTP polling/parser/database and plotting defects, added a Bootstrap dashboard with hourly to annual reports, filters and explicit missing-data handling, plus automated tests and systemd units. See `BUGFIXES.md` for the original defect review.