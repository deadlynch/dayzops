from dataclasses import dataclass, field
from pathlib import Path

from dayzops.lock import global_lock
from dayzops.logger import get_logger
from dayzops.mods import startup_params
from dayzops.systemd import (
    render_server_unit,
    render_update_service,
    render_update_timer,
    render_prune_service,
    render_prune_timer,
    SERVER_SERVICE,
    UPDATE_SERVICE,
    PRUNE_SERVICE,
)

log = get_logger("apply")

_SYMBOL = {"install": "+", "create": "+", "update": "~", "remove": "-"}


@dataclass
class Change:
    resource: str  # "server" | "mod" | "unit"
    action: str    # "install" | "create" | "update" | "remove"
    detail: str

    def __str__(self) -> str:
        return f"  {_SYMBOL.get(self.action, '*')} {self.resource}: {self.detail}"


@dataclass
class Plan:
    changes: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.changes

    def render(self) -> str:
        if self.empty:
            return "Nada a fazer — estado já convergido."
        return "\n".join(["Mudanças planejadas:"] + [str(c) for c in self.changes])


# ---------------------------------------------------------------------------
# Estado desejado derivado do config
# ---------------------------------------------------------------------------

def build_exec_start(svc) -> str:
    """Linha ExecStart do servidor, derivada do config (mods em ordem)."""
    server = svc.config.get("server", {})
    instance = svc.config.get("instance", {})
    port = server.get("port", 2302)
    server_cfg = instance.get("config", "serverDZ.cfg")

    parts = [str(svc.install_dir / "DayZServer"), f"-config={server_cfg}", f"-port={port}"]
    parts += startup_params(svc.mods, svc.servermods)
    return " ".join(parts)


def desired_units(svc) -> dict:
    """Conteúdo desejado de cada unit (nome -> texto)."""
    updates = svc.config.get("updates", {})
    schedule = updates.get("schedule", "04:00")
    prune_schedule = updates.get("prune_schedule", "05:00")
    return {
        f"{SERVER_SERVICE}.service": render_server_unit(
            exec_start=build_exec_start(svc), working_dir=str(svc.install_dir)
        ),
        f"{UPDATE_SERVICE}.service": render_update_service(),
        f"{UPDATE_SERVICE}.timer": render_update_timer(schedule=schedule),
        f"{PRUNE_SERVICE}.service": render_prune_service(),
        f"{PRUNE_SERVICE}.timer": render_prune_timer(schedule=prune_schedule),
    }


# ---------------------------------------------------------------------------
# Diff: desejado vs. real
# ---------------------------------------------------------------------------

def build_plan(svc, *, units_dir: Path) -> Plan:
    plan = Plan()

    # 1) Servidor: presença (apply garante instalado; refresh é o 'update').
    if not (svc.install_dir / "DayZServer").exists():
        plan.changes.append(Change("server", "install", f"instalar em {svc.install_dir}"))

    # 2) Mods: diff calculado sem mutar nada.
    mod_actions = svc.modsync.plan(svc.all_mods)
    for name in mod_actions["create"]:
        plan.changes.append(Change("mod", "create", f"symlink {name}"))
    for name in mod_actions["update"]:
        plan.changes.append(Change("mod", "update", f"corrigir symlink {name}"))
    for name in mod_actions["remove"]:
        plan.changes.append(Change("mod", "remove", f"remover symlink {name}"))

    # 3) Units: conteúdo desejado vs. arquivo em disco.
    units_dir = Path(units_dir)
    for name, content in desired_units(svc).items():
        path = units_dir / name
        if not path.exists():
            plan.changes.append(Change("unit", "create", name))
        elif path.read_text(encoding="utf-8") != content:
            plan.changes.append(Change("unit", "update", name))

    return plan


# ---------------------------------------------------------------------------
# Converge
# ---------------------------------------------------------------------------

def run_apply(svc, *, units_dir: Path, dry_run: bool = False, lock_file=None) -> Plan:
    """Lê o desejado, compara com o real e converge só a diferença.

    Idempotente: rodar de novo num estado já convergido devolve um Plan vazio
    e não toca em nada. Com dry_run=True, só mostra o plano.
    """
    plan = build_plan(svc, units_dir=units_dir)

    if dry_run or plan.empty:
        return plan

    units_dir = Path(units_dir)
    cm = global_lock(lock_file) if lock_file else global_lock()
    with cm:
        log.info("apply: convergindo %d mudança(s)", len(plan.changes))

        if any(c.resource == "server" and c.action == "install" for c in plan.changes):
            svc.steam.install_or_update_server(svc.install_dir)

        svc.modsync.sync(svc.all_mods)
        svc.keys.rebuild(svc.mod_dirs)  # keys seguem os mods (ADR-0004)

        units_dir.mkdir(parents=True, exist_ok=True)
        for name, content in desired_units(svc).items():
            (units_dir / name).write_text(content, encoding="utf-8")

        svc.store.set_installed_mods(
            [{"id": m.id, "name": m.name} for m in svc.all_mods]
        )
        svc.store.write_inventory()
        log.info("apply: convergido")

    return plan
