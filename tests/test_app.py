import types

from dayzops import app


def _result(returncode=0, stdout="active"):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _config(tmp_path):
    server = tmp_path / "server"
    workshop = tmp_path / "workshop"
    (server / "profiles").mkdir(parents=True)
    (server / "DayZServer").write_text("binario")
    (server / "serverDZ.cfg").write_text("hostname = Test;")
    (workshop / "1559212036").mkdir(parents=True)
    return {
        "server": {"name": "Test", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server),
            "workshop_dir": str(workshop),
            "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": [{"id": 1559212036, "name": "CF"}],
        "servermods": [],
    }


def test_build_services_parses_config(tmp_path):
    svc = app.build_services(_config(tmp_path))
    assert svc.install_dir.name == "server"
    assert [m.name for m in svc.mods] == ["@CF"]


def test_do_update_full_workflow(tmp_path):
    cfg = _config(tmp_path)
    svc = app.build_services(
        cfg,
        steam_runner=lambda cmd: _result(0),       # steamcmd nunca roda de verdade
        control_runner=lambda cmd: _result(0),     # systemctl nunca roda de verdade
    )

    inv = app.do_update(svc, lock_file=tmp_path / "dayzops.lock")

    # Estado registrado
    assert svc.store.last_update()["status"] == "success"
    # Mod sincronizado: symlink criado
    assert (tmp_path / "server" / "@CF").is_symlink()
    # Mod registrado no inventário
    assert inv["installed_mods"] == [{"id": 1559212036, "name": "@CF"}]
    # Backup foi criado
    assert list((tmp_path / "backups").glob("dayz-backup-*.tar.gz"))


def test_do_update_records_backup_in_state(tmp_path):
    cfg = _config(tmp_path)
    svc = app.build_services(cfg, steam_runner=lambda c: _result(0),
                             control_runner=lambda c: _result(0))
    app.do_update(svc, lock_file=tmp_path / "dayzops.lock")
    assert svc.store.last_backup() is not None
