from pathlib import Path

DEFAULT_CONFIG = Path("server.yaml")

APP_NAME = "dayzops"

STATE_DIR = Path("/srv/dayz/state")

LOCK_FILE = Path("/run/dayzops.lock")

INSTALLED_MODS_FILE = "installed-mods.json"

INSTALLED_KEYS_FILE = "installed-keys.json"

LAST_BACKUP_FILE = "last-backup.json"

LAST_UPDATE_FILE = "last-update.json"

INVENTORY_FILE = "inventory.json"