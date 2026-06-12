import types

import yaml

from dayzops import app
from dayzops.cli import main
from dayzops.config import save_config, load_config
from dayzops.mods import add_mod, remove_mod


def _result(returncode=0, stdout="active"):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _write_config(tmp_path, mods=None):
    server = tmp_path / "server"
    server.mkdir()
    body = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server), "workshop_dir": str(tmp_path / "workshop"),
            "mods_dir": str(tmp_path / "mods"), "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": mods or [],
    }
    path = tmp_path / "server.yaml"
    path.write_text(yaml.safe_dump(body))
    return path


# --- manipulação da lista (puro sobre o dict) ---

def test_add_mod():
    cfg = {"mods": []}
    assert add_mod(cfg, 123, name="CF") is True
    assert cfg["mods"] == [{"id": 123, "name": "CF"}]
    assert add_mod(cfg, 123) is False  # duplicado


def test_add_servermod():
    cfg = {}
    add_mod(cfg, 9, server=True)
    assert cfg["servermods"] == [{"id": 9}]


def test_remove_mod():
    cfg = {"mods": [{"id": 1}, {"id": 2}], "servermods": []}
    assert remove_mod(cfg, 1) is True
    assert cfg["mods"] == [{"id": 2}]
    assert remove_mod(cfg, 999) is False


def test_save_config_roundtrip(tmp_path):
    path = tmp_path / "c.yaml"
    save_config({"server": {"port": 2302}, "mods": [{"id": 1}]}, path)
    assert load_config(path)["mods"] == [{"id": 1}]


# --- CLI ---

def test_cli_mod_add_then_list(tmp_path, capsys):
    cfg = _write_config(tmp_path)
    assert main(["-c", str(cfg), "mod", "add", "1559212036", "--name", "CF"]) == 0
    # persistiu no arquivo
    assert load_config(cfg)["mods"] == [{"id": 1559212036, "name": "CF"}]
    # e aparece no list
    capsys.readouterr()
    main(["-c", str(cfg), "mod", "list"])
    assert "1559212036" in capsys.readouterr().out


def test_cli_mod_remove(tmp_path):
    cfg = _write_config(tmp_path, mods=[{"id": 1, "name": "CF"}])
    assert main(["-c", str(cfg), "mod", "remove", "1"]) == 0
    assert load_config(cfg)["mods"] == []


def test_do_rollback_sequence(tmp_path):
    # backup existente para restaurar
    server = tmp_path / "server"
    (server / "profiles").mkdir(parents=True)
    (server / "serverDZ.cfg").write_text("cfg")
    cfg = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server), "workshop_dir": str(tmp_path / "workshop"),
            "mods_dir": str(tmp_path / "mods"), "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": [],
    }
    calls = []
    svc = app.build_services(cfg, control_runner=lambda c: (calls.append(c[-2]), _result())[1])
    svc.backup.create()  # algo para restaurar

    app.do_rollback(svc, lock_file=tmp_path / "dayzops.lock")
    # parou e subiu o serviço em volta da restauração
    assert "stop" in calls and "start" in calls
