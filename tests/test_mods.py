from dayzops.mods import Mod, parse_mods, mod_param, startup_params, ModSync


def test_mod_name_defaults_to_id():
    mod = Mod.from_config({"id": 1559212036})
    assert mod.name == "@1559212036"


def test_mod_name_gets_at_prefix():
    assert Mod.from_config({"id": 1, "name": "CF"}).name == "@CF"
    assert Mod.from_config({"id": 1, "name": "@CF"}).name == "@CF"


def test_order_is_preserved():
    mods = parse_mods([{"id": 1, "name": "CF"}, {"id": 2, "name": "Dabs"}])
    # ADR-0007: a ordem do config é a ordem de carga.
    assert mod_param(mods) == "@CF;@Dabs"


def test_startup_params_separate_categories():
    mods = parse_mods([{"id": 1, "name": "CF"}])
    servermods = parse_mods([{"id": 9, "name": "AdminTools"}])
    params = startup_params(mods, servermods)
    assert params == ["-mod=@CF", "-serverMod=@AdminTools"]


def test_startup_params_omits_empty():
    assert startup_params(parse_mods([{"id": 1, "name": "CF"}]), []) == ["-mod=@CF"]


def _setup(tmp_path, ids):
    workshop = tmp_path / "workshop"
    server = tmp_path / "server"
    workshop.mkdir()
    server.mkdir()
    for i in ids:
        (workshop / str(i)).mkdir()
    return ModSync(workshop, server), workshop, server


def test_sync_creates_symlinks(tmp_path):
    sync, workshop, server = _setup(tmp_path, [1559212036])
    mods = parse_mods([{"id": 1559212036, "name": "CF"}])

    summary = sync.sync(mods)
    link = server / "@CF"
    assert link.is_symlink()
    assert link.resolve() == (workshop / "1559212036").resolve()
    assert summary["created"] == ["@CF"]


def test_sync_is_idempotent(tmp_path):
    sync, _, _ = _setup(tmp_path, [1])
    mods = parse_mods([{"id": 1, "name": "CF"}])

    sync.sync(mods)
    summary = sync.sync(mods)  # segunda vez
    assert summary["created"] == []
    assert summary["unchanged"] == ["@CF"]


def test_sync_removes_dropped_mod(tmp_path):
    sync, _, server = _setup(tmp_path, [1, 2])
    sync.sync(parse_mods([{"id": 1, "name": "CF"}, {"id": 2, "name": "Dabs"}]))

    # Remove Dabs do config.
    summary = sync.sync(parse_mods([{"id": 1, "name": "CF"}]))
    assert "@Dabs" in summary["removed"]
    assert not (server / "@Dabs").exists()
    assert (server / "@CF").is_symlink()


def test_sync_fixes_wrong_target(tmp_path):
    sync, workshop, server = _setup(tmp_path, [1, 2])
    # Cria um symlink apontando pro alvo errado.
    (server / "@CF").symlink_to(workshop / "2")

    summary = sync.sync(parse_mods([{"id": 1, "name": "CF"}]))
    assert "@CF" in summary["updated"]
    assert (server / "@CF").resolve() == (workshop / "1").resolve()


def test_sync_does_not_touch_real_dirs(tmp_path):
    sync, _, server = _setup(tmp_path, [1])
    # Uma pasta real chamada @Manual (não é symlink nosso).
    (server / "@Manual").mkdir()

    sync.sync(parse_mods([{"id": 1, "name": "CF"}]))
    # Não removida, porque não é symlink gerenciado.
    assert (server / "@Manual").is_dir()
