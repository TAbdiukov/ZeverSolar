"""Shared local settings for the collector and dashboard."""

from configparser import ConfigParser, Error
from pathlib import Path


DEFAULT_CONFIG = Path(__file__).with_name("config.ini")


def load_config(path=None):
    """Load config.ini beside the scripts unless --config supplies another file."""
    filename = Path(path) if path is not None else DEFAULT_CONFIG
    settings = ConfigParser(interpolation=None)
    try:
        with filename.open(encoding="utf-8") as handle:
            settings.read_file(handle)
    except FileNotFoundError as exc:
        if path is not None:
            raise ValueError(f"Configuration file not found: {filename}") from exc
    except (OSError, Error) as exc:
        raise ValueError(f"Cannot read configuration file {filename}: {exc}") from exc
    return settings