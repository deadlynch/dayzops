import sys

from pathlib import Path

from dayzops import __version__
from dayzops.config import load_config, validate_config, ConfigError
from dayzops.constants import DEFAULT_CONFIG


def _resolve_config_path(args: list[str]) -> Path:
    """Procura -c/--config nos argumentos; cai no DEFAULT_CONFIG se ausente.

    Necessário porque o caminho padrão agora é absoluto (/srv/dayz/...),
    então durante o desenvolvimento dá pra apontar para um arquivo local.
    """
    for i, arg in enumerate(args):
        if arg in ("-c", "--config"):
            if i + 1 < len(args):
                return Path(args[i + 1])
            raise ConfigError("-c/--config exige um caminho")
    return DEFAULT_CONFIG


def cmd_version() -> int:
    print(f"dayzops {__version__}")
    return 0


def cmd_validate_config(config_path: Path) -> int:
    # Antes: só chamava load_config() — a validação de campos nunca rodava.
    # Agora: carrega E valida, listando cada erro encontrado.
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Configuration invalid: {exc}")
        return 1

    errors = validate_config(config)
    if errors:
        print("Configuration invalid:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Configuration valid")
    return 0


def cmd_status(config_path: Path) -> int:
    print("DayZOPS Status")
    print("----------------")
    print(f"Config File: {config_path}")

    if config_path.exists():
        print("Configuration: OK")
    else:
        print("Configuration: Missing")

    # TODO(etapa 4): ler estado real do servidor/mods via state.py
    print("Server: Not Installed")
    print("Mods: Unknown")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: dayzops [version|validate-config|status] [-c CONFIG]")
        return 1

    command = sys.argv[1]
    rest = sys.argv[2:]

    if command == "version":
        return cmd_version()

    try:
        config_path = _resolve_config_path(rest)
    except ConfigError as exc:
        print(str(exc))
        return 1

    if command == "validate-config":
        return cmd_validate_config(config_path)

    if command == "status":
        return cmd_status(config_path)

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
