from dataclasses import dataclass, field
from pathlib import Path

from dayzops.fsperm import chown_path, chown_recursive
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

_SYMBOL = {"install": "+", "create": "+", "update": "~", "remove": "-", "download": "v"}


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
    """Linha ExecStart do servidor, derivada do config (mods em ordem).

    Inclui flags recomendadas pela Bohemia (DayZ:Server_Configuration wiki):
    -BEpath, -profiles são essenciais para handshake correto do BattlEye e
    isolamento de logs/RCon dentro do install_dir (sem isso, profiles caem
    em $HOME/.local/share/DayZ Other Profiles/ com path bagunçado, e BE
    procura config em path default que varia entre versões).
    -doLogs, -adminLog, -netLog, -freezeCheck são higiene operacional padrão.

    Opcionais configurados em server.yaml:
    - server.cpu_count (int)        → -cpuCount=N
    - server.limit_fps (int)        → -limitFPS=N
    - server.file_patching (bool)   → -filePatching (só pra dev de mod)
    - server.extra_args (list[str]) → flags não cobertas, em ordem
    - paths.storage_dir (str)       → -storage=path
    """
    server = svc.config.get("server", {})
    instance = svc.config.get("instance", {})
    paths = svc.config.get("paths", {})
    port = server.get("port", 2302)
    server_cfg = instance.get("config", "serverDZ.cfg")
    profile = instance.get("profile", "profiles")

    parts = [
        str(svc.install_dir / "DayZServer"),
        f"-config={server_cfg}",
        f"-port={port}",
    ]
    parts += startup_params(svc.mods, svc.servermods)

    # Flags Bohemia obrigatórias (hardcoded)
    parts += [
        f"-BEpath={svc.install_dir}/battleye",
        f"-profiles={svc.install_dir}/{profile}",
        "-doLogs",
        "-adminLog",
        "-netLog",
        "-freezeCheck",
    ]

    # Flags opcionais do server.yaml
    cpu_count = server.get("cpu_count")
    if cpu_count:
        parts.append(f"-cpuCount={int(cpu_count)}")

    limit_fps = server.get("limit_fps")
    if limit_fps:
        parts.append(f"-limitFPS={int(limit_fps)}")

    if server.get("file_patching"):
        parts.append("-filePatching")

    storage_dir = paths.get("storage_dir")
    if storage_dir:
        parts.append(f"-storage={storage_dir}")

    extra_args = server.get("extra_args") or []
    for arg in extra_args:
        parts.append(str(arg))

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

def _content_missing(svc, mod) -> bool:
    """True se o conteúdo do mod não está no disco (mesmo critério do keys.py).

    Cobre o diretório ausente e o symlink pendurado (alvo inexistente),
    pois Path.exists() segue o link.
    """
    return not (svc.workshop_dir / str(mod.id)).exists()


def build_plan(svc, *, units_dir: Path) -> Plan:
    plan = Plan()

    # 1) Servidor: presença (apply garante instalado; refresh é o 'update').
    if not (svc.install_dir / "DayZServer").exists():
        plan.changes.append(Change("server", "install", f"instalar em {svc.install_dir}"))

    # 2) Mods: conteúdo declarado mas ausente no disco -> baixar.
    for mod in svc.all_mods:
        if _content_missing(svc, mod):
            plan.changes.append(Change("mod", "download", f"baixar conteúdo {mod.name}"))

    # 3) Mods: diff de symlinks (calculado sem mutar nada).
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

def _ensure_runtime_dirs(svc) -> None:
    """Garante diretórios que o ExecStart referencia (idempotente).

    O ExecStart usa -profiles={install_dir}/{instance.profile}; se a pasta
    não existe, o servidor falha ao escrever logs/BE config. install.sh
    já cria isso na primeira instalação, mas servers existentes (antes do
    fix) ou paths customizados via instance.profile podem cair aqui.
    Chowna pra service_user porque o servidor (que roda como dayz) precisa
    escrever logs/BE config dentro.
    """
    instance = svc.config.get("instance", {})
    profile = instance.get("profile", "profiles")
    profile_path = svc.install_dir / profile
    profile_path.mkdir(parents=True, exist_ok=True)
    chown_path(profile_path, svc.service_user)


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
            # SteamCMD pode baixar arquivos como root quando o wrap sudo -u
            # falha por alguma razão de ambiente; chown defensivo cobre.
            # No-op em dev/CI sem root.
            chown_recursive(svc.install_dir, svc.service_user)

        # Baixa o conteúdo de mods declarados que faltam no disco, antes de
        # criar os symlinks e reconstruir as keys (senão o link fica pendurado).
        for mod in svc.all_mods:
            if _content_missing(svc, mod):
                svc.steam.download_mod(mod.id, workshop_dir=svc.workshop_dir)

        svc.modsync.sync(svc.all_mods)
        # Sync incremental — preserva dayz.bikey (Bohemia) e qualquer key
        # que o operador tenha colocado manualmente. Remove só keys de mods
        # que saíram do server.yaml. (divergência #14 — substitui ADR-0004)
        svc.keys.sync(svc.mod_dirs_with_id)

        # Garante profiles/ etc. antes da unit ser ativada
        _ensure_runtime_dirs(svc)

        units_dir.mkdir(parents=True, exist_ok=True)
        for name, content in desired_units(svc).items():
            (units_dir / name).write_text(content, encoding="utf-8")

        svc.store.set_installed_mods(
            [{"id": m.id, "name": m.name} for m in svc.all_mods]
        )
        svc.store.write_inventory()
        log.info("apply: convergido")

    return plan
