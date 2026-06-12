import argparse

from pathlib import Path

from dayzops import __version__, app
from dayzops.backup import BackupError
from dayzops.config import load_config, validate_config, ConfigError
from dayzops.constants import DEFAULT_CONFIG
from dayzops.lock import LockError
from dayzops.ops import UpdateError
from dayzops.systemd import SystemdError

# Comandos que só precisam de leitura simples, sem montar Services.
_STANDALONE = {"version", "validate-config"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dayzops")
    # Opção global: vem ANTES do comando (estilo git: dayzops -c PATH update).
    parser.add_argument(
        "-c", "--config", type=Path, default=DEFAULT_CONFIG,
        help="caminho do server.yaml",
    )
    sub = parser.add_subparsers(dest="command")
    for name in (
        "version", "validate-config", "status",
        "update", "backup", "start", "stop", "restart",
    ):
        sub.add_parser(name)
    return parser


def _validated_config(config_path: Path) -> dict:
    """Carrega e valida; levanta ConfigError com a lista de erros."""
    config = load_config(config_path)
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    return config


# --- Handlers ---

def _cmd_version() -> int:
    print(f"dayzops {__version__}")
    return 0


def _cmd_validate_config(config_path: Path) -> int:
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


def _cmd_status(svc: app.Services) -> int:
    print("DayZOPS Status")
    print("----------------")

    # is-active toca o systemctl; em dev/sem systemd, é best-effort.
    try:
        active = svc.control.is_active()
        print(f"Service: {'active' if active else 'inactive'}")
    except Exception:
        print("Service: desconhecido")

    print(f"Mods instalados: {len(svc.store.installed_mods())}")

    last_update = svc.store.last_update()
    print(f"Último update: {last_update['timestamp'] if last_update else 'nunca'}")

    last_backup = svc.store.last_backup()
    print(f"Último backup: {last_backup['timestamp'] if last_backup else 'nunca'}")
    return 0


def _cmd_update(svc: app.Services) -> int:
    try:
        app.do_update(svc)
        print("Update concluído")
        return 0
    except LockError as exc:
        print(f"Abortado: {exc}")
        return 1
    except UpdateError as exc:
        print(f"Update falhou (backup restaurado): {exc}")
        return 1


def _cmd_backup(svc: app.Services) -> int:
    try:
        archive = svc.backup.create()
        print(f"Backup criado: {archive}")
        return 0
    except BackupError as exc:
        print(f"Backup falhou: {exc}")
        return 1


def _cmd_service_action(svc: app.Services, action: str) -> int:
    try:
        getattr(svc.control, action)()
        print(f"Serviço: {action} ok")
        return 0
    except SystemdError as exc:
        print(f"Falha no systemctl: {exc}")
        return 1


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    command = args.command

    if command is None:
        _build_parser().print_usage()
        return 1

    if command == "version":
        return _cmd_version()

    if command == "validate-config":
        return _cmd_validate_config(args.config)

    # Demais comandos precisam de config válido + Services montados.
    try:
        config = _validated_config(args.config)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}")
        return 1

    svc = app.build_services(config)

    if command == "status":
        return _cmd_status(svc)
    if command == "update":
        return _cmd_update(svc)
    if command == "backup":
        return _cmd_backup(svc)
    if command in ("start", "stop", "restart"):
        return _cmd_service_action(svc, command)

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
