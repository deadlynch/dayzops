import shutil

from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("keys")

KEYS_DIRNAME = "keys"  # destino no servidor: <install_dir>/keys/


class KeyManager:
    """Rebuild completo do diretório de keys (.bikey) — ADR-0004.

    A sincronização incremental deixa keys órfãs, duplicadas ou obsoletas
    (mods renomeiam keys entre updates). A estratégia é destrutiva e simples:
    apaga o keys/ inteiro e reconstrói a partir das .bikey dos mods ativos.
    Previsível e sem estado pendurado.
    """

    def __init__(self, server_dir: Path):
        self.server_dir = Path(server_dir)
        self.keys_dir = self.server_dir / KEYS_DIRNAME

    def discover(self, mod_dirs) -> dict:
        """Acha todas as .bikey nos mods (recursivo, case-insensitive).

        Dedup por nome de arquivo (primeira ocorrência vence). Retorna
        {nome_do_arquivo: caminho_de_origem}.
        """
        found: dict[str, Path] = {}
        for mod_dir in mod_dirs:
            mod_dir = Path(mod_dir)
            if not mod_dir.exists():
                log.warning("mod ausente, pulando keys: %s", mod_dir)
                continue
            for entry in mod_dir.rglob("*"):
                # case-insensitive: cobre .bikey/.Bikey/.BIKEY (o -iname do ADR)
                if entry.is_file() and entry.suffix.lower() == ".bikey":
                    found.setdefault(entry.name, entry)
        return found

    def rebuild(self, mod_dirs) -> list[str]:
        """Apaga e reconstrói o keys/ a partir dos mods. Retorna nomes copiados."""
        # 1) remove o diretório inteiro
        if self.keys_dir.exists():
            shutil.rmtree(self.keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)

        # 2-4) descobre + dedup
        keys = self.discover(mod_dirs)

        # 5) reconstrói
        for name, src in keys.items():
            shutil.copy2(src, self.keys_dir / name)

        log.info("keys rebuild: %d chave(s)", len(keys))
        return sorted(keys)
