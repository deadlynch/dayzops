from pathlib import Path

import yaml

from dayzops.validators import require, ValidationError


class ConfigError(Exception):
    pass


# Campos sem os quais o servidor não tem como subir.
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
    """Lê o YAML do disco e garante que a raiz é um mapping.

    Levanta ConfigError em qualquer problema de leitura/parse.
    Não valida o conteúdo — isso é responsabilidade de validate_config().
    """
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    if not isinstance(config, dict):
        raise ConfigError("Configuration root must be a YAML mapping")

    return config


def validate_config(config: dict) -> list[str]:
    """Valida o conteúdo do config. Retorna lista de erros (vazia = válido).

    Duas camadas de checagem:
      1. Presença de todos os REQUIRED_FIELDS.
      2. Tipo/valor dos campos que conseguimos resolver (porta, retenção).
    """
    errors: list[str] = []

    # 1) Campos obrigatórios presentes
    for field in REQUIRED_FIELDS:
        try:
            require(config, field)
        except ValidationError:
            errors.append(f"campo obrigatório ausente: {field}")

    # 2) Tipo/valor (só checa se o campo existe — ausência já foi reportada acima)
    port = _safe_get(config, "server.port")
    if port is not None:
        if not isinstance(port, int) or isinstance(port, bool):
            errors.append("server.port deve ser inteiro")
        elif not (1 <= port <= 65535):
            errors.append("server.port deve estar entre 1 e 65535")

    retention = _safe_get(config, "backup.retention_days")
    if retention is not None:
        if not isinstance(retention, int) or isinstance(retention, bool) or retention <= 0:
            errors.append("backup.retention_days deve ser inteiro positivo")

    return errors


def _safe_get(config: dict, path: str):
    """Como require(), mas devolve None em vez de levantar ValidationError."""
    try:
        return require(config, path)
    except ValidationError:
        return None
