from dayzops.keys import KeyManager


def _mod_with_key(base, mod_name, key_name, *, subdir="keys"):
    d = base / mod_name / subdir
    d.mkdir(parents=True)
    (d / key_name).write_bytes(b"KEYDATA")
    return base / mod_name


def test_discover_finds_bikey_recursively(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, "1", "cf.bikey")
    km = KeyManager(tmp_path / "server")
    found = km.discover([m1])
    assert "cf.bikey" in found


def test_discover_case_insensitive_dir_and_ext(tmp_path):
    mods = tmp_path / "workshop"
    # diretório "Keys" e extensão maiúscula
    m = _mod_with_key(mods, "1", "Namalsk.BIKEY", subdir="Keys")
    km = KeyManager(tmp_path / "server")
    assert "Namalsk.BIKEY" in km.discover([m])


def test_discover_dedups_by_name(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, "1", "cf.bikey")
    m2 = _mod_with_key(mods, "2", "cf.bikey")
    km = KeyManager(tmp_path / "server")
    found = km.discover([m1, m2])
    assert list(found.keys()) == ["cf.bikey"]  # uma só


def test_rebuild_copies_keys(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, "1", "cf.bikey")
    km = KeyManager(tmp_path / "server")
    copied = km.rebuild([m1])
    assert copied == ["cf.bikey"]
    assert (tmp_path / "server" / "keys" / "cf.bikey").exists()


def test_rebuild_removes_orphaned_keys(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, "1", "cf.bikey")
    km = KeyManager(tmp_path / "server")
    km.rebuild([m1])

    # key antiga que não pertence a nenhum mod atual
    (km.keys_dir / "orphan.bikey").write_bytes(b"old")

    km.rebuild([m1])  # rebuild completo deve eliminá-la
    assert not (km.keys_dir / "orphan.bikey").exists()
    assert (km.keys_dir / "cf.bikey").exists()


def test_rebuild_is_idempotent(tmp_path):
    mods = tmp_path / "workshop"
    m1 = _mod_with_key(mods, "1", "cf.bikey")
    km = KeyManager(tmp_path / "server")
    assert km.rebuild([m1]) == km.rebuild([m1])
