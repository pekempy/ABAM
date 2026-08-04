"""
Aurora Engine - Application Configuration & Global Constants
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENGINE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "aurora_ui"

# Default FTP Connection Settings
DEFAULT_FTP_HOST = "192.168.5.56"
DEFAULT_FTP_USER = "xbox"
DEFAULT_FTP_PASS = "xbox"
DEFAULT_FTP_PORT = 7564
DEFAULT_FTP_TIMEOUT = 10  # Seconds

# Remote Xbox Aurora Paths
REMOTE_AURORA_DB_PATH = "Hdd1:\\Aurora\\Data\\DataBases\\Content.db"
REMOTE_AURORA_MEDIA_DIR = "Hdd1:\\Aurora\\Data\\Media"

# Cache Settings
CACHE_DIR_NAME = ".aurora_cache"
