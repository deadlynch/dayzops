import os

from dataclasses import dataclass
from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("mods")


@dataclass(frozen=True)
class Mod:
    """Um mod: id do Workshop + nome da pasta/symlink (ex: '@CF')."""
    id: int
    name: str

    @classmethod
    def from_config(cls, entry: dict) -> "Mod":
        mod_id = entry["id"]
        name = entry.get("name") or f"@{mod_id}"
        if not name.startswith("@"):
            name = f"@{name}"
        return cls(id=mod_id, name=name)


def parse_mods(entries) -> list[Mod]:
    return [Mod.from_config(e) for e in (entries or [])]


def mod_param(mods: list[Mod]) -> str:
    """Gera o valor de -mod=/-serverMod= preservando a ordem (ADR-0007)."""
    return ";".join(m.name for m in mods)


def startup_params(mods: list[Mod], servermods: list[Mod]) -> list[str]:
    """Parâmetros de startup, com cliente e servidor separados (ADR-0008)."""
    params: list[str] = []
    if mods:
        params.append(f"-mod={mod_param(mods)}")
    if servermods:
        params.append(f"-serverMod={mod_param(servermods)}")
    return params


class ModSync:
    """Sincroniza symlinks @Nome -> workshop/<id> (ADR-0003).

    Separa planejar (plan) de executar (sync). O plan() inspeciona o disco e
    diz o que mudaria, sem alterar nada — é o que torna o dry-run possível.
    Idempotente: só mexe em symlinks '@...' que apontam pro workshop.
    """

    def __init__(self, workshop_dir: Path, server_dir: Path):
        self.workshop_dir = Path(workshop_dir)
        self.server_dir = Path(server_dir)

    def _link_path(self, mod: Mod) -> Path:
        return self.server_dir / mod.name

    def _target_path(self, mod: Mod) -> Path:
        return self.workshop_dir / str(mod.id)

    def _is_managed_link(self, entry: Path) -> bool:
        if not (entry.is_symlink() and entry.name.startswith("@")):
            return False
        try:
            target = os.readlink(entry)
        except OSError:
            return False
        return str(Path(target)).startswith(str(self.workshop_dir))

    def plan(self, mods: list[Mod]) -> dict:
        """Calcula, sem mutar nada, o que sync() faria.

        Retorna {create, update, remove, unchanged} com nomes de symlink.
        """
        desired = {m.name for m in mods}
        result = {"create": [], "update": [], "remove": [], "unchanged": []}

        for mod in mods:
            link = self._link_path(mod)
            target = self._target_path(mod)
            if link.is_symlink():
                if os.readlink(link) == str(target):
                    result["unchanged"].append(mod.name)
                else:
                    result["update"].append(mod.name)
            elif link.exists():
                log.warning("%s existe e não é symlink; ignorando", link)
            else:
                result["create"].append(mod.name)

        if self.server_dir.exists():
            for entry in self.server_dir.iterdir():
                if entry.name not in desired and self._is_managed_link(entry):
                    result["remove"].append(entry.name)

        return result

    def sync(self, mods: list[Mod]) -> dict:
        """Converge os symlinks para o conjunto `mods` (executa o plan)."""
        self.server_dir.mkdir(parents=True, exist_ok=True)
        actions = self.plan(mods)
        by_name = {m.name: m for m in mods}

        for name in actions["create"]:
            mod = by_name[name]
            self._link_path(mod).symlink_to(self._target_path(mod))
        for name in actions["update"]:
            mod = by_name[name]
            link = self._link_path(mod)
            link.unlink()
            link.symlink_to(self._target_path(mod))
        for name in actions["remove"]:
            (self.server_dir / name).unlink()

        log.info(
            "mods sync: +%d ~%d -%d =%d",
            len(actions["create"]), len(actions["update"]),
            len(actions["remove"]), len(actions["unchanged"]),
        )
        return {
            "created": actions["create"],
            "updated": actions["update"],
            "removed": actions["remove"],
            "unchanged": actions["unchanged"],
        }
