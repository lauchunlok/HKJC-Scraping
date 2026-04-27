"""
Central configuration for HKJC Scraping project.
"""
import os
import logging
from logging.handlers import RotatingFileHandler

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hkjc.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CSV_DIR = os.path.join(BASE_DIR, "clean")

# ──────────────────────────────────────────────
# Scraping defaults
# ──────────────────────────────────────────────
DEFAULT_WORKERS = 10
PAGE_LOAD_TIMEOUT = 5  # seconds to wait for dynamic content
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries

# ──────────────────────────────────────────────
# Base URLs
# ──────────────────────────────────────────────
RACE_RESULT_URL = (
    "https://racing.hkjc.com/racing/information/english/Racing/"
    "LocalResults.aspx?RaceDate={date}&RaceNo={race_no}"
)

FORM_RECORD_URL = (
    "https://racing.hkjc.com/racing/information/English/Horse/"
    "Horse.aspx?HorseId={horse_id}&Option=1"
)

SECTIONAL_TIME_URL = (
    "https://racing.hkjc.com/racing/information/english/Racing/"
    "DisplaySectionalTime.aspx?RaceDate={date}&RaceNo={race_no}"
)

# ──────────────────────────────────────────────
# Date range for race result scraping
# Default: 2007-08 season start to current
# ──────────────────────────────────────────────
from datetime import datetime

YEAR_START = 2007
YEAR_END = datetime.now().year

# HKJC racing season runs Sep → Jul
# Races happen Wed/Sat/Sun + public holidays
# Max races per day = 12 (sometimes fewer)
MAX_RACES_PER_DAY = 13


# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────
def setup_logging(name: str, level=logging.INFO) -> logging.Logger:
    """Create a logger with console + file handlers."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers on re-import
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Rotating file handler (5 MB per file, keep 3 backups)
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger
