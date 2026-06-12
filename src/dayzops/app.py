from dataclasses import dataclass
from pathlib import Path

from dayzops.backup import BackupManager
from dayzops.constants import LOCK_FILE
from dayzops.health import HealthChecker
from dayzops.keys import KeyManager
from dayzops.lock import global_lock
from dayzops.logger import get_logger
from dayzops.mods import parse_mods, ModSync
from dayzops.ops import UpdatePlan, run_update
from dayzops.state import StateStore
from dayzops.steamcmd import SteamCmd
from dayzops.systemd import ServerControl
from dayzops.verify import verify_install

log = get_logger("app")


def _get(config: dict, *path, default=None):
    cur = config
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


@dataclass
class Services:
    """Tudo que a aplicação precisa, montado a partir do config.

    Raiz de composição: o único lugar que sabe ligar os módulos entre si.
    """
    config: dict
    store: StateStore
    steam: SteamCmd
    backup: BackupManager
    modsync: ModSync
    keys: KeyManager
    control: ServerControl
    install_dir: Path
    workshop_dir: Path
    mods: list
    servermods: list

    @property
    def all_mods(self) -> list:
        return self.mods + self.servermods

    @property
    def mod_dirs(self) -> list:
        """Diretórios de conteúdo dos mods ativos (workshop/<id>)."""
        return [self.workshop_dir / str(m.id) for m in self.all_mods]


def build_services(config: dict, *, steam_runner=None, control_runner=None) -> Services:
    install_dir = Path(_get(config, "paths", "install_dir"))
    workshop_dir = Path(_get(config, "paths", "workshop_dir"))
    backups_dir = Path(_get(config, "paths", "backups_dir"))
    state_dir = Path(_get(config, "paths", "state_dir"))
    username = _get(config, "steam", "username")

    store = StateStore(state_dir)

    return Services(
        config=config,
        store=store,
        steam=SteamCmd(username, runner=steam_runner),
        backup=BackupManager(install_dir, backups_dir, store=store),
        modsync=ModSync(workshop_dir, install_dir),
        keys=KeyManager(install_dir),
        control=ServerControl(runner=control_runner),
        install_dir=install_dir,
        workshop_dir=workshop_dir,
        mods=parse_mods(_get(config, "mods", default=[])),
        servermods=parse_mods(_get(config, "servermods", default=[])),
    )


def _sync_mods(svc: Services) -> dict:
    for mod in svc.all_mods:
        svc.steam.download_mod(mod.id)
    summary = svc.modsync.sync(svc.all_mods)
    svc.store.set_installed_mods([{"id": m.id, "name": m.name} for m in svc.all_mods])
    return summary


def build_update_plan(svc: Services) -> UpdatePlan:
    """Liga os passos reais no workflow do ops.py. Sem stubs restantes."""
    return UpdatePlan(
        update_server=lambda: svc.steam.install_or_update_server(svc.install_dir),
        create_backup=svc.backup.create,
        restore_backup=lambda: svc.backup.restore(),
        stop_server=svc.control.stop,
        start_server=svc.control.start,
        update_mods=lambda: _sync_mods(svc),
        validate=lambda: verify_install(svc),
        sync_keys=lambda: svc.keys.rebuild(svc.mod_dirs),
        health_check=lambda: HealthChecker(svc.control).wait(),
    )


def do_update(svc: Services, *, lock_file: Path = LOCK_FILE) -> dict:
    return run_update(build_update_plan(svc), store=svc.store, lock_file=lock_file)


def units_dir_for(svc: Services) -> Path:
    configured = _get(svc.config, "paths", "systemd_dir")
    return Path(configured) if configured else Path("/etc/systemd/system")


def do_apply(svc: Services, *, units_dir: Path, dry_run: bool = False, lock_file: Path = LOCK_FILE):
    from dayzops import apply  # import tardio: evita ciclo apply<->app
    return apply.run_apply(svc, units_dir=units_dir, dry_run=dry_run, lock_file=lock_file)


def do_rollback(svc: Services, *, lock_file: Path = LOCK_FILE) -> None:
    """Restaura o backup mais recente e sobe o servidor (operação crítica)."""
    with global_lock(lock_file):
        svc.control.stop()
        svc.backup.restore()
        svc.control.start()
        log.info("rollback concluído")
