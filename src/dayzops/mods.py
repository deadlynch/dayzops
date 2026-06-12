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
        # O ADR-0007 só exige 'id'; o nome do symlink é opcional. Sem nome,
        # cai num default determinístico '@<id>'. DayZ aceita qualquer nome
        # de pasta desde que o -mod= use o mesmo.
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

    Idempotente: rodar de novo com a mesma config não muda nada. Symlinks de
    mods que saíram do config são removidos; os que apontam pro alvo errado
    são corrigidos. Só mexe em symlinks '@...' que apontam pra dentro do
    workshop — nunca toca em arquivos/pastas reais do servidor.
    """

    def __init__(self, workshop_dir: Path, server_dir: Path):
        self.workshop_dir = Path(workshop_dir)
        self.server_dir = Path(server_dir)

    def _link_path(self, mod: Mod) -> Path:
        return self.server_dir / mod.name

    def _target_path(self, mod: Mod) -> Path:
        return self.workshop_dir / str(mod.id)

    def _is_managed_link(self, entry: Path) -> bool:
        # Critério de segurança para remoção: é symlink, tem prefixo '@' e
        # aponta pra dentro do workshop. Qualquer outra coisa é intocável.
        if not (entry.is_symlink() and entry.name.startswith("@")):
            return False
        try:
            target = os.readlink(entry)
        except OSError:
            return False
        return str(Path(target)).startswith(str(self.workshop_dir))

    def sync(self, mods: list[Mod]) -> dict:
        """Converge os symlinks para exatamente o conjunto `mods`.

        Retorna um resumo das ações: created / updated / removed / unchanged.
        """
        self.server_dir.mkdir(parents=True, exist_ok=True)
        desired = {m.name for m in mods}
        summary = {"created": [], "updated": [], "removed": [], "unchanged": []}

        # 1) Cria ou corrige os desejados.
        for mod in mods:
            link = self._link_path(mod)
            target = self._target_path(mod)

            if link.is_symlink():
                if os.readlink(link) == str(target):
                    summary["unchanged"].append(mod.name)
                else:
                    link.unlink()
                    link.symlink_to(target)
                    summary["updated"].append(mod.name)
            elif link.exists():
                # Existe mas não é symlink (cópia real?) — não mexemos.
                log.warning("%s existe e não é symlink; pulando", link)
            else:
                link.symlink_to(target)
                summary["created"].append(mod.name)

        # 2) Remove symlinks gerenciados que não estão mais no config.
        for entry in self.server_dir.iterdir():
            if entry.name not in desired and self._is_managed_link(entry):
                entry.unlink()
                summary["removed"].append(entry.name)

        log.info(
            "mods sync: +%d ~%d -%d =%d",
            len(summary["created"]), len(summary["updated"]),
            len(summary["removed"]), len(summary["unchanged"]),
        )
        return summary
