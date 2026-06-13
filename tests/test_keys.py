"""Testes do KeyManager — sync incremental (divergência #14, substitui ADR-0004).

Comportamento esperado, conforme decisão "conservadora":
- discover() pega .bikey nos mod_dirs (case-insensitive, recursivo, dedup por nome).
- sync() é INCREMENTAL: copia novas, atualiza alteradas, remove SÓ as que vieram
  de mod removido. Keys de origem desconhecida (órfãs) são SEMPRE preservadas.
- rebuild() é alias backward-compat de sync() (mesmo comportamento conservador).
"""
import types

from dayzops.keys import KeyManager


# --- Helpers --------------------------------------------------------------

def _mod_with_key(base, mod_id, key_name, *, subdir="keys", content=b"KEYDATA"):
    d = base / str(mod_id) / subdir
    d.mkdir(parents=True)
    (d / key_name).write_bytes(content)
    return base / str(mod_id)


class _MemStore:
    """StateStore em memória para testes."""
    def __init__(self):
        self._keys: list = []

    def installed_keys(self):
        return list(self._keys)

    def set_installed_keys(self, keys):
        self._keys = list(keys)


# --- discover -------------------------------------------------------------

def test_discover_finds_bikey_recursively(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "cf.bikey")
    km = KeyManager(tmp_path / "server")
    found = km.discover([(1, m1)])
    assert "cf.bikey" in found
    src, mod_id = found["cf.bikey"]
    assert mod_id == 1
    assert src.name == "cf.bikey"


def test_discover_case_insensitive_dir_and_ext(tmp_path):
    mods = tmp_path / "workshop"
    m = _mod_with_key(mods, 1, "Namalsk.BIKEY", subdir="Keys")
    km = KeyManager(tmp_path / "server")
    assert "Namalsk.BIKEY" in km.discover([(1, m)])


def test_discover_dedups_by_name(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "cf.bikey")
    m2 = _mod_with_key(mods, 2, "cf.bikey")
    km = KeyManager(tmp_path / "server")
    found = km.discover([(1, m1), (2, m2)])
    assert list(found.keys()) == ["cf.bikey"]


# --- sync: comportamento conservador (divergência #14) -------------------

def test_sync_copies_new_keys_and_registers_origin(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1559212036, "Jacob_Mango_V3.bikey")
    store = _MemStore()
    km = KeyManager(tmp_path / "server", store=store)

    result = km.sync([(1559212036, m1)])

    assert result["added"] == ["Jacob_Mango_V3.bikey"]
    assert (km.keys_dir / "Jacob_Mango_V3.bikey").exists()
    assert store.installed_keys() == [
        {"name": "Jacob_Mango_V3.bikey", "mod_id": 1559212036}
    ]


def test_sync_preserves_dayz_bikey_even_with_no_mods(tmp_path):
    """O cenário que causou o bug: rmtree apagava dayz.bikey da Bohemia.
    sync() conservador não deve tocar em órfãs sem registro.
    """
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.keys_dir.mkdir(parents=True)
    (km.keys_dir / "dayz.bikey").write_bytes(b"BOHEMIA_KEY")

    result = km.sync([])  # nenhum mod

    assert (km.keys_dir / "dayz.bikey").exists()
    assert (km.keys_dir / "dayz.bikey").read_bytes() == b"BOHEMIA_KEY"
    assert result["preserved_orphans"] == ["dayz.bikey"]
    assert result["removed"] == []


def test_sync_preserves_dayz_bikey_with_mods_present(tmp_path):
    """dayz.bikey deve sobreviver mesmo durante sync com mods novos."""
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1559212036, "Jacob_Mango_V3.bikey")
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.keys_dir.mkdir(parents=True)
    (km.keys_dir / "dayz.bikey").write_bytes(b"BOHEMIA_KEY")

    km.sync([(1559212036, m1)])

    assert (km.keys_dir / "dayz.bikey").read_bytes() == b"BOHEMIA_KEY"
    assert (km.keys_dir / "Jacob_Mango_V3.bikey").exists()


def test_sync_removes_only_keys_from_removed_mods(tmp_path):
    """Se mod sai do server.yaml, sua key deve sair junto. E só ela."""
    mods = tmp_path / "workshop"
    m_cf = _mod_with_key(mods, 1559212036, "cf.bikey")
    m_bbp = _mod_with_key(mods, 1828439404, "basebuildingplus.bikey")
    store = _MemStore()
    km = KeyManager(tmp_path / "server", store=store)

    # Estado inicial: ambos os mods sincronizados
    km.sync([(1559212036, m_cf), (1828439404, m_bbp)])
    assert (km.keys_dir / "cf.bikey").exists()
    assert (km.keys_dir / "basebuildingplus.bikey").exists()

    # Operador removeu BaseBuildingPlus do server.yaml; CF permanece
    result = km.sync([(1559212036, m_cf)])

    assert result["removed"] == ["basebuildingplus.bikey"]
    assert not (km.keys_dir / "basebuildingplus.bikey").exists()
    assert (km.keys_dir / "cf.bikey").exists()


def test_sync_preserves_manual_keys_from_operator(tmp_path):
    """Operador pôs key manualmente em keys/. Mesmo após sync com mods,
    a key manual continua lá.
    """
    mods = tmp_path / "workshop"
    m_cf = _mod_with_key(mods, 1559212036, "cf.bikey")
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.keys_dir.mkdir(parents=True)
    (km.keys_dir / "minha_key_local.bikey").write_bytes(b"MANUAL")

    km.sync([(1559212036, m_cf)])

    assert (km.keys_dir / "minha_key_local.bikey").read_bytes() == b"MANUAL"
    assert (km.keys_dir / "cf.bikey").exists()


def test_sync_updates_changed_mod_key(tmp_path):
    """Mod atualizou conteúdo de sua key — sobrescreve."""
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "cf.bikey", content=b"OLD")
    km = KeyManager(tmp_path / "server", store=_MemStore())

    km.sync([(1, m1)])
    assert (km.keys_dir / "cf.bikey").read_bytes() == b"OLD"

    # Mod atualizado no workshop
    (mods / "1" / "keys" / "cf.bikey").write_bytes(b"NEW")
    result = km.sync([(1, m1)])

    assert result["updated"] == ["cf.bikey"]
    assert (km.keys_dir / "cf.bikey").read_bytes() == b"NEW"


def test_sync_does_not_overwrite_orphan_with_same_name(tmp_path):
    """Se já existe key órfã com mesmo nome que uma do mod, NÃO sobrescreve.
    Operador decide manualmente se quer trocar.
    """
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "duplicate.bikey", content=b"MOD_VERSION")
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.keys_dir.mkdir(parents=True)
    (km.keys_dir / "duplicate.bikey").write_bytes(b"OPERATOR_VERSION")

    km.sync([(1, m1)])

    # Versão do operador ganha
    assert (km.keys_dir / "duplicate.bikey").read_bytes() == b"OPERATOR_VERSION"


def test_sync_is_idempotent(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "cf.bikey")
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.sync([(1, m1)])
    result2 = km.sync([(1, m1)])
    # Segunda passada: nada novo, nada removido
    assert result2["added"] == []
    assert result2["updated"] == []
    assert result2["removed"] == []


# --- rebuild() backward-compat -------------------------------------------

def test_rebuild_legacy_api_still_works(tmp_path):
    """Código antigo que chama rebuild([dirs]) ainda funciona, com
    comportamento NÃO destrutivo (preserva órfãs).
    """
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, 1, "cf.bikey")
    km = KeyManager(tmp_path / "server", store=_MemStore())
    km.keys_dir.mkdir(parents=True)
    (km.keys_dir / "dayz.bikey").write_bytes(b"BOHEMIA")

    copied = km.rebuild([m1])

    assert "cf.bikey" in copied
    assert (km.keys_dir / "dayz.bikey").exists()  # PRESERVADA
    assert (km.keys_dir / "cf.bikey").exists()
