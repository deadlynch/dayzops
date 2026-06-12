import json
import os
import tempfile

from datetime import datetime, timezone
from pathlib import Path

from dayzops.constants import STATE_DIR
from dayzops.logger import get_logger

log = get_logger("state")

# Inventários definidos no ADR-0010.
INSTALLED_MODS = "installed-mods.json"
INSTALLED_KEYS = "installed-keys.json"
LAST_BACKUP = "last-backup.json"
LAST_UPDATE = "last-update.json"
INVENTORY = "inventory.json"


class StateStore:
    """Lê e escreve os inventários de estado gerados (ADR-0010).

    Os arquivos vivem em STATE_DIR e, segundo o ADR, nunca devem ser editados
    à mão — esta classe é a única forma suportada de mexer neles.
    """

    def __init__(self, state_dir: Path = STATE_DIR):
        self.state_dir = state_dir

    def _path(self, name: str) -> Path:
        return self.state_dir / name

    def read(self, name: str, default=None):
        """Lê um inventário; devolve `default` se o arquivo não existe."""
        path = self._path(name)
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def write(self, name: str, data) -> None:
        """Grava um inventário de forma atômica (write-temp + rename).

        O os.replace() é atômico dentro do mesmo filesystem: ou fica o
        conteúdo antigo inteiro, ou o novo inteiro — nunca um JSON pela
        metade, mesmo se o processo morrer no meio da escrita. Por isso o
        arquivo temporário é criado NO MESMO diretório (rename entre
        filesystems diferentes não é atômico).
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(name)

        fd, tmp = tempfile.mkstemp(dir=self.state_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)  # troca atômica
            log.debug("estado gravado: %s", name)
        except BaseException:
            # Em qualquer falha, não deixa .tmp órfão para trás.
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    # --- Helpers tipados para os inventários conhecidos ---

    def installed_mods(self) -> list:
        return self.read(INSTALLED_MODS, default=[])

    def set_installed_mods(self, mods: list) -> None:
        self.write(INSTALLED_MODS, mods)

    def installed_keys(self) -> list:
        return self.read(INSTALLED_KEYS, default=[])

    def set_installed_keys(self, keys: list) -> None:
        self.write(INSTALLED_KEYS, keys)

    def last_backup(self) -> dict | None:
        return self.read(LAST_BACKUP, default=None)

    def record_backup(self, **details) -> None:
        self.write(LAST_BACKUP, _timestamped(details))

    def last_update(self) -> dict | None:
        return self.read(LAST_UPDATE, default=None)

    def record_update(self, **details) -> None:
        self.write(LAST_UPDATE, _timestamped(details))

    def inventory(self) -> dict:
        """Snapshot consolidado — base para responder 'o que mudou?'."""
        return {
            "installed_mods": self.installed_mods(),
            "installed_keys": self.installed_keys(),
            "last_backup": self.last_backup(),
            "last_update": self.last_update(),
            "generated_at": _now_iso(),
        }

    def write_inventory(self) -> dict:
        """Gera e persiste o inventory.json consolidado."""
        inv = self.inventory()
        self.write(INVENTORY, inv)
        return inv


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamped(details: dict) -> dict:
    record = {"timestamp": _now_iso()}
    record.update(details)
    return record