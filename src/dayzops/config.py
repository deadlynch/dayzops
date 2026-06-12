from pathlib import Path

import yaml

from dayzops.validators import require, ValidationError


class ConfigError(Exception):
    pass


REQUIRED_FIELDS = [
    "server.name",
    "server.map",
    "server.port",
    "steam.username",
    "paths.install_dir",
    "paths.mods_dir",
    "paths.workshop_dir",
    "paths.backups_dir",
    "paths.state_dir",
]


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}"
        )

    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    if not isinstance(config, dict):
        raise ConfigError(
            "Configuration root must be a YAML mapping"
        )

    return config


def validate_config(config: dict) -> list[str]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        try:
            require(config, field)
        except ValidationError:
            errors.append(field)

    return errors