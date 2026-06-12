import argparse

from pathlib import Path

from dayzops import __version__, app
from dayzops.backup import BackupError
from dayzops.config import load_config, validate_config, save_config, ConfigError
from dayzops.constants import DEFAULT_CONFIG
from dayzops.lock import LockError
from dayzops.mods import parse_mods, add_mod, remove_mod
from dayzops.ops import UpdateError
from dayzops.systemd import SystemdError

_STANDALONE = {"version", "validate-config"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dayzops")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                        help="caminho do server.yaml")
    sub = parser.add_subparsers(dest="command")
    for name in ("version", "validate-config", "status", "update",
                 "backup", "rollback", "prune", "start", "stop", "restart",
                 "steam-login"):
        sub.add_parser(name)

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--dry-run", action="store_true",
                         help="mostra o que mudaria sem alterar nada")

    mod_p = sub.add_parser("mod")
    mod_sub = mod_p.add_subparsers(dest="mod_action")
    mod_sub.add_parser("list")
    add_p = mod_sub.add_parser("add")
    add_p.add_argument("id", type=int)
    add_p.add_argument("--name")
    add_p.add_argument("--server", action="store_true", help="adiciona em servermods")
    rm_p = mod_sub.add_parser("remove")
    rm_p.add_argument("id", type=int)

    return parser


def _validated_config(config_path: Path) -> dict:
    config = load_config(config_path)
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    return config


# --- Handlers que não precisam de Services ---

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


def _cmd_mod(config: dict, config_path: Path, args) -> int:
    action = getattr(args, "mod_action", None)

    if action == "list":
        for label, key in (("Client mods", "mods"), ("Server mods", "servermods")):
            print(f"{label}:")
            for m in parse_mods(config.get(key, [])):
                print(f"  {m.id}  {m.name}")
        return 0

    if action == "add":
        if add_mod(config, args.id, name=args.name, server=args.server):
            save_config(config, config_path)
            print(f"Mod {args.id} adicionado")
            return 0
        print(f"Mod {args.id} já está na lista")
        return 1

    if action == "remove":
        if remove_mod(config, args.id):
            save_config(config, config_path)
            print(f"Mod {args.id} removido")
            return 0
        print(f"Mod {args.id} não encontrado")
        return 1

    print("Uso: dayzops mod [list|add|remove]")
    return 1


# --- Handlers que precisam de Services ---

def _cmd_status(svc: app.Services) -> int:
    print("DayZOPS Status")
    print("----------------")
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


def _cmd_rollback(svc: app.Services) -> int:
    try:
        app.do_rollback(svc)
        print("Rollback concluído")
        return 0
    except LockError as exc:
        print(f"Abortado: {exc}")
        return 1
    except BackupError as exc:
        print(f"Rollback falhou: {exc}")
        return 1


def _cmd_backup(svc: app.Services) -> int:
    try:
        archive = svc.backup.create()
        print(f"Backup criado: {archive}")
        return 0
    except BackupError as exc:
        print(f"Backup falhou: {exc}")
        return 1


def _cmd_prune(svc: app.Services) -> int:
    removed = app.do_prune(svc)
    print(f"Prune: {len(removed)} backup(s) removido(s)")
    return 0


def _cmd_service_action(svc: app.Services, action: str) -> int:
    try:
        getattr(svc.control, action)()
        print(f"Serviço: {action} ok")
        return 0
    except SystemdError as exc:
        print(f"Falha no systemctl: {exc}")
        return 1


def _cmd_apply(svc: app.Services, dry_run: bool) -> int:
    try:
        plan = app.do_apply(svc, units_dir=app.units_dir_for(svc), dry_run=dry_run)
    except LockError as exc:
        print(f"Abortado: {exc}")
        return 1
    print(plan.render())
    if dry_run and not plan.empty:
        print("\n(dry-run: nada foi alterado)")
    return 0


def _cmd_steam_login(svc: app.Services) -> int:
    """Login interativo: cacheia credencial do Steam (Guard) uma vez.

    Roda steamcmd no contexto do usuário de serviço (com HOME ajustado),
    com stdio herdado para o operador digitar o código do Guard quando
    aplicável. Após sucesso, o ssfn fica em $HOME/.steam do dayz, e os
    apply/update seguintes passam sem prompt.
    """
    print(
        "Login interativo do Steam (digite Steam Guard se solicitado).\n"
        f"Usuário: {svc.steam.username}\n"
        f"Será executado como: {svc.service_user}\n"
    )
    code = svc.steam.interactive_login()
    if code == 0:
        print("\nLogin ok — credencial cacheada. Pode rodar 'dayzops apply'.")
        return 0
    print(f"\nLogin falhou (exit {code}). Confira usuário/senha e tente de novo.")
    return code


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

    try:
        config = _validated_config(args.config)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}")
        return 1

    # 'mod' mexe no config, não precisa de Services.
    if command == "mod":
        return _cmd_mod(config, args.config, args)

    svc = app.build_services(config)

    if command == "status":
        return _cmd_status(svc)
    if command == "update":
        return _cmd_update(svc)
    if command == "rollback":
        return _cmd_rollback(svc)
    if command == "backup":
        return _cmd_backup(svc)
    if command == "prune":
        return _cmd_prune(svc)
    if command in ("start", "stop", "restart"):
        return _cmd_service_action(svc, command)
    if command == "apply":
        return _cmd_apply(svc, getattr(args, "dry_run", False))
    if command == "steam-login":
        return _cmd_steam_login(svc)

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
