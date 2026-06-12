import types

from dayzops import app, apply


def _result(returncode=0, stdout="Success"):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _svc(tmp_path, *, server_installed=True):
    server = tmp_path / "server"
    workshop = tmp_path / "workshop"
    server.mkdir(parents=True)
    if server_installed:
        (server / "DayZServer").write_text("binario")
    (workshop / "1559212036").mkdir(parents=True)
    cfg = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server),
            "workshop_dir": str(workshop),
            "mods_dir": str(tmp_path / "mods"),
            "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": [{"id": 1559212036, "name": "CF"}],
        "servermods": [],
    }
    return app.build_services(cfg, steam_runner=lambda c: _result(),
                              control_runner=lambda c: _result())


def test_plan_lists_mods_and_units(tmp_path):
    svc = _svc(tmp_path)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    kinds = {(c.resource, c.action) for c in plan.changes}
    assert ("mod", "create") in kinds       # @CF ainda não existe
    assert ("unit", "create") in kinds      # nenhuma unit em disco
    assert not plan.empty


def test_plan_flags_missing_server(tmp_path):
    svc = _svc(tmp_path, server_installed=False)
    plan = apply.build_plan(svc, units_dir=tmp_path / "units")
    assert any(c.resource == "server" for c in plan.changes)


def test_dry_run_changes_nothing(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    plan = apply.run_apply(svc, units_dir=units, dry_run=True,
                           lock_file=tmp_path / "dayzops.lock")
    assert not plan.empty
    # nada foi criado
    assert not (tmp_path / "server" / "@CF").exists()
    assert not units.exists()


def test_apply_converges(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    apply.run_apply(svc, units_dir=units, lock_file=tmp_path / "dayzops.lock")

    assert (tmp_path / "server" / "@CF").is_symlink()
    assert (units / "dayz.service").exists()
    assert svc.store.installed_mods() == [{"id": 1559212036, "name": "@CF"}]


def test_apply_is_idempotent(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    lock = tmp_path / "dayzops.lock"

    apply.run_apply(svc, units_dir=units, lock_file=lock)
    # segunda vez: nada divergiu -> plano vazio
    second = apply.run_apply(svc, units_dir=units, lock_file=lock)
    assert second.empty


def test_apply_reconverges_after_drift(tmp_path):
    svc = _svc(tmp_path)
    units = tmp_path / "units"
    lock = tmp_path / "dayzops.lock"
    apply.run_apply(svc, units_dir=units, lock_file=lock)

    # drift: alguém apagou um symlink na mão
    (tmp_path / "server" / "@CF").unlink()

    plan = apply.run_apply(svc, units_dir=units, lock_file=lock)
    assert any(c.resource == "mod" and c.action == "create" for c in plan.changes)
    assert (tmp_path / "server" / "@CF").is_symlink()  # reconvergido
