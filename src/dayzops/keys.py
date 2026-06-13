import shutil

from pathlib import Path

from dayzops.fsperm import chown_path
from dayzops.logger import get_logger

log = get_logger("keys")

KEYS_DIRNAME = "keys"  # destino no servidor: <install_dir>/keys/


class KeyManager:
    """Sincronização incremental do diretório de keys (.bikey).

    HISTÓRICO E DECISÃO (revisão da ADR-0004):

    A versão anterior usava `rmtree(keys_dir)` + rebuild a cada apply.
    Isso é destrutivo demais: apaga a `dayz.bikey` (Bohemia, vem com o
    server base) e qualquer key que o operador tenha colocado manualmente
    (mods locais, server mods custom, keys de testes). Foi a causa
    diagnosticada do kick 118 ("Server installation is corrupt") em produção.

    Esta versão opera por DIFF baseado em ORIGEM:

    1. O state.installed_keys persiste o que JÁ COPIAMOS por mod:
         [{"name": "Jacob_Mango_V3.bikey", "mod_id": 1559212036}, ...]
    2. Em cada sync, calculamos:
         - desejadas: keys atuais dos mod_dirs (com mod_id de origem)
         - registradas: state.installed_keys (o que pusemos antes)
         - novas: copiar (e registrar)
         - obsoletas (registradas mas o mod sumiu OU renomeou a key): apagar (e desregistrar)
         - presentes: sobrescrever se conteúdo mudou (mod atualizou a key)
    3. Keys EXISTENTES NA PASTA mas NÃO REGISTRADAS são ORFÃS de origem
       desconhecida (dayz.bikey da Bohemia, keys manuais do operador): NUNCA TOCAR.

    Ownership: todo arquivo criado/copiado tem chown ao service_user via
    fsperm.chown_path (no-op em dev/CI sem root).

    Resultado: dayz.bikey sobrevive sempre. Operador pode pôr keys
    manualmente sem medo do DayZops apagar. Mod removido = só a key dele
    sai. Comportamento determinístico e auditável via installed-keys.json.
    """

    def __init__(self, server_dir: Path, store=None, service_user: str | None = None):
        self.server_dir = Path(server_dir)
        self.keys_dir = self.server_dir / KEYS_DIRNAME
        self.store = store
        self.service_user = service_user

    def discover(self, mod_dirs_with_id) -> dict:
        """Acha todas as .bikey nos mods (recursivo, case-insensitive), associando à origem.

        `mod_dirs_with_id` é iterável de tuplas (mod_id, mod_dir).

        Dedup por nome de arquivo (primeira ocorrência vence). Retorna
        {nome_do_arquivo: (caminho_de_origem, mod_id)}.
        """
        found: dict[str, tuple[Path, int | str]] = {}
        for mod_id, mod_dir in mod_dirs_with_id:
            mod_dir = Path(mod_dir)
            if not mod_dir.exists():
                log.warning("mod ausente, pulando keys: %s", mod_dir)
                continue
            for entry in mod_dir.rglob("*"):
                if entry.is_file() and entry.suffix.lower() == ".bikey":
                    found.setdefault(entry.name, (entry, mod_id))
        return found

    def _read_registered(self) -> dict:
        """Lê installed-keys.json e devolve {nome_arquivo: mod_id}."""
        if self.store is None:
            return {}
        raw = self.store.installed_keys() or []
        return {entry["name"]: entry["mod_id"] for entry in raw if "name" in entry and "mod_id" in entry}

    def _write_registered(self, registered: dict) -> None:
        if self.store is None:
            return
        self.store.set_installed_keys(
            [{"name": n, "mod_id": mid} for n, mid in sorted(registered.items())]
        )

    def _files_differ(self, src: Path, dst: Path) -> bool:
        try:
            return src.read_bytes() != dst.read_bytes()
        except FileNotFoundError:
            return True

    def sync(self, mod_dirs_with_id) -> dict:
        """Sincroniza keys/ de forma incremental (não destrutiva).

        Retorna {"added": [...], "updated": [...], "removed": [...], "preserved_orphans": [...]}
        para logs/testes. NUNCA chama rmtree no keys/.
        """
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        chown_path(self.keys_dir, self.service_user)

        desired = self.discover(mod_dirs_with_id)  # name -> (src_path, mod_id)
        registered = self._read_registered()       # name -> mod_id (do disco antes)

        on_disk = {entry.name for entry in self.keys_dir.iterdir() if entry.is_file()}
        orphans = on_disk - set(registered.keys())  # presentes mas não registrados → preservar

        added: list[str] = []
        updated: list[str] = []
        removed: list[str] = []

        # 1) novas + sobrescritas (apenas se conteúdo divergir)
        new_registry: dict = dict(registered)  # copia pra mutar
        for name, (src, mod_id) in desired.items():
            dst = self.keys_dir / name
            if name not in registered and name not in orphans:
                shutil.copy2(src, dst)
                chown_path(dst, self.service_user)
                new_registry[name] = mod_id
                added.append(name)
            elif name in registered:
                if self._files_differ(src, dst):
                    shutil.copy2(src, dst)
                    chown_path(dst, self.service_user)
                    updated.append(name)
                new_registry[name] = mod_id
            else:
                log.warning(
                    "key %r existe como órfã em %s; NÃO sobrescrita pelo mod %s. "
                    "Remova manualmente se quiser que a versão do mod seja usada.",
                    name, self.keys_dir, mod_id,
                )

        # 2) obsoletas: registradas antes, mas o mod saiu (não está mais em desired)
        for name, mod_id in registered.items():
            if name not in desired:
                dst = self.keys_dir / name
                if dst.exists():
                    dst.unlink()
                    removed.append(name)
                new_registry.pop(name, None)

        self._write_registered(new_registry)

        log.info(
            "keys sync: +%d ~%d -%d (orfãs preservadas: %d)",
            len(added), len(updated), len(removed), len(orphans),
        )
        return {
            "added": sorted(added),
            "updated": sorted(updated),
            "removed": sorted(removed),
            "preserved_orphans": sorted(orphans),
        }

    # --- Backward-compat: aliases para a API antiga ---

    def rebuild(self, mod_dirs) -> list[str]:
        """COMPATIBILIDADE: mantém a assinatura antiga (apenas mod_dirs, sem IDs).

        Encaminha pra sync() preenchendo mod_id por inferência do nome da pasta
        (string com dígitos vira int, senão fica o nome). Quem chamar esta
        forma legada perde a granularidade de rastreio por mod_id real, mas
        ainda ganha o comportamento não destrutivo. Código novo deve chamar
        sync() diretamente.
        """
        def _infer_id(path: Path):
            stem = Path(path).name
            return int(stem) if stem.isdigit() else stem

        result = self.sync([(_infer_id(Path(d)), d) for d in mod_dirs])
        return sorted(result["added"] + result["updated"])
