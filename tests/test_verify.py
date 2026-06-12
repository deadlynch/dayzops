import types

import pytest

from dayzops import app, verify


def _result():
    return types.SimpleNamespace(returncode=0, stdout="Success", stderr="")


def _svc(tmp_path, *, binary=True, cfg_file=True, mod_content=True):
    server = tmp_path / "server"
    workshop = tmp_path / "workshop"
    server.mkdir(parents=True, exist_ok=True)
    if binary:
        (server / "DayZServer").write_text("bin")
    if cfg_file:
        (server / "serverDZ.cfg").write_text("hostname=T;")
    if mod_content:
        (workshop / "1559212036").mkdir(parents=True, exist_ok=True)
    config = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server), "workshop_dir": str(workshop),
            "mods_dir": str(tmp_path / "mods"), "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
        "mods": [{"id": 1559212036, "name": "CF"}], "servermods": [],
    }
    return app.build_services(config, steam_runner=lambda c: _result(),
                              control_runner=lambda c: _result())


def test_clean_install_passes(tmp_path):
    assert verify.check_install(_svc(tmp_path)) == []
    verify.verify_install(_svc(tmp_path))  # não levanta


def test_missing_binary_detected(tmp_path):
    problems = verify.check_install(_svc(tmp_path, binary=False))
    assert any("binário" in p for p in problems)


def test_missing_config_detected(tmp_path):
    problems = verify.check_install(_svc(tmp_path, cfg_file=False))
    assert any("config" in p for p in problems)


def test_missing_mod_content_detected(tmp_path):
    problems = verify.check_install(_svc(tmp_path, mod_content=False))
    assert any("mod" in p for p in problems)


def test_verify_install_raises_on_problem(tmp_path):
    with pytest.raises(verify.VerifyError):
        verify.verify_install(_svc(tmp_path, binary=False))
