import textwrap

from dayzops.cli import main


def _write_config(tmp_path, valid=True):
    server = tmp_path / "server"
    server.mkdir()
    body = {
        "server": {"name": "T", "map": "chernarus", "port": 2302},
        "steam": {"username": "alice"},
        "paths": {
            "install_dir": str(server),
            "workshop_dir": str(tmp_path / "workshop"),
            "mods_dir": str(tmp_path / "mods"),
            "backups_dir": str(tmp_path / "backups"),
            "state_dir": str(tmp_path / "state"),
        },
    }
    if not valid:
        del body["server"]["port"]  # quebra um campo obrigatório
    import yaml
    path = tmp_path / "server.yaml"
    path.write_text(yaml.safe_dump(body))
    return path


def test_version(capsys):
    assert main(["version"]) == 0
    assert "dayzops" in capsys.readouterr().out


def test_no_command_returns_error():
    assert main([]) == 1


def test_validate_config_valid(tmp_path):
    cfg = _write_config(tmp_path, valid=True)
    assert main(["-c", str(cfg), "validate-config"]) == 0


def test_validate_config_invalid(tmp_path, capsys):
    cfg = _write_config(tmp_path, valid=False)
    assert main(["-c", str(cfg), "validate-config"]) == 1
    assert "invalid" in capsys.readouterr().out.lower()


def test_status_reads_state(tmp_path, capsys):
    cfg = _write_config(tmp_path, valid=True)
    assert main(["-c", str(cfg), "status"]) == 0
    out = capsys.readouterr().out
    assert "Mods instalados: 0" in out
    assert "nunca" in out  # nenhum update/backup ainda
