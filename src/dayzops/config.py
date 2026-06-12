from pathlib import Path
import yaml


class ConfigError(Exception):
    pass


def load_config(path: Path):
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)