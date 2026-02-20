"""Application configuration: paths and constants."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

DEFAULT_DB_NAME = "default_snt.db"
DEFAULT_DB_PATH = DATA_DIR / DEFAULT_DB_NAME

MAX_BACKUPS = 5

APP_TITLE = "СНТ Бухгалтерия"
APP_VERSION = "1.0.0"
WINDOW_SIZE = "1280x800"
MIN_WINDOW_SIZE = (1024, 600)

PENALTY_DAILY_RATE_DEFAULT = "0.001"  # 0.1% per day
