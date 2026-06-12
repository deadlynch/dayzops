import os
import tarfile
import time

from datetime import datetime, timezone
from pathlib import Path

from dayzops.logger import get_logger
from dayzops.state import StateStore

log = get_logger("backup")

# Escopo padrão do ADR-0005 (caminhos relativos ao install_dir do servidor).
# mpmissions/.../storage_1/ (persistência do mundo) entra junto com mpmissions.
DEFAULT_SCOPE = [
    "profiles",
    "mpmissions",
    "battleye",
    "config",
    "custom",
    "serverDZ.cfg",
]


class BackupError(Exception):
    pass


class BackupManager:
    """Cria, lista, restaura e expira backups (ADR-0005)."""

    def __init__(
        self,
        server_dir: Path,
        backups_dir: Path,
        *,
        scope: list[str] | None = None,
        store: StateStore | None = None,
    ):
        self.server_dir = Path(server_dir)
        self.backups_dir = Path(backups_dir)
        self.scope = scope or DEFAULT_SCOPE
        self.store = store

    def create(self) -> Path:
        """Cria um .tar.gz com timestamp contendo os caminhos do escopo.

        Escreve num .tmp e só renomeia no fim: nunca sobra um arquivo de
        backup pela metade que pareça válido.
        """
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = self.backups_dir / f"dayz-backup-{ts}.tar.gz"
        tmp = self.backups_dir / (archive.name + ".tmp")

        included: list[str] = []
        with tarfile.open(tmp, "w:gz") as tar:
            for entry in self.scope:
                src = self.server_dir / entry
                if src.exists():
                    tar.add(src, arcname=entry)
                    included.append(entry)
                else:
                    log.warning("escopo ausente, pulando: %s", entry)

        if not included:
            tmp.unlink(missing_ok=True)
            raise BackupError("nenhum caminho do escopo existe; backup abortado")

        tmp.replace(archive)
        log.info("backup criado: %s (%d itens)", archive.name, len(included))

        if self.store is not None:
            self.store.record_backup(archive=str(archive), included=included)
        return archive

    def list_backups(self) -> list[Path]:
        if not self.backups_dir.exists():
            return []
        return sorted(self.backups_dir.glob("dayz-backup-*.tar.gz"))

    def latest(self) -> Path | None:
        backups = self.list_backups()
        return backups[-1] if backups else None

    def restore(self, archive: Path | None = None) -> Path:
        """Restaura um backup (o mais recente, se nenhum for indicado)."""
        target = Path(archive) if archive else self.latest()
        if target is None or not target.exists():
            raise BackupError("nenhum backup disponível para restaurar")

        with tarfile.open(target, "r:gz") as tar:
            _safe_extract(tar, self.server_dir)

        log.info("backup restaurado: %s", target.name)
        return target

    def prune(self, retention_days: int) -> list[Path]:
        """Remove backups mais antigos que retention_days."""
        cutoff = time.time() - retention_days * 86400
        removed: list[Path] = []
        for backup in self.list_backups():
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
                removed.append(backup)
                log.info("backup expirado removido: %s", backup.name)
        return removed


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extrai checando path traversal antes (defende contra 'tarbomb').

    Um .tar.gz malicioso pode conter membros tipo '../../etc/algo'. Sem
    checar, o extractall escreveria FORA do destino. Validamos que cada
    membro resolve para dentro de `dest` e só então extraímos.

    (Python 3.12+ tem extractall(filter='data') para isso; o check manual
    funciona em toda a faixa >=3.11 e deixa a defesa explícita.)
    """
    dest = dest.resolve()
    dest_prefix = str(dest) + os.sep

    for member in tar.getmembers():
        resolved = (dest / member.name).resolve()
        if resolved != dest and not str(resolved).startswith(dest_prefix):
            raise BackupError(f"caminho suspeito no backup: {member.name}")

    # filter='data' (3.12+, backport em 3.11.4+) reforça a defesa nativamente
    # e silencia o DeprecationWarning. Fallback para Pythons sem o parâmetro.
    try:
        tar.extractall(dest, filter="data")
    except TypeError:
        tar.extractall(dest)
