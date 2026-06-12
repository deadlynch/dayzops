from dayzops.config import validate_config


def _valid_config() -> dict:
    """Config mínimo e válido, reaproveitado pelos testes."""
    return {
        "server": {
            "name": "Test",
            "map": "chernarus",
            "port": 2302,
        },
        "steam": {
            "username": "test",
        },
        "paths": {
            "install_dir": "/tmp",
            "mods_dir": "/tmp",
            "workshop_dir": "/tmp",
            "backups_dir": "/tmp",
            "state_dir": "/tmp",
        },
    }


def test_valid_config():
    assert validate_config(_valid_config()) == []


def test_missing_required_fields():
    cfg = {"server": {"name": "Test"}}
    errors = validate_config(cfg)

    assert any("server.map" in e for e in errors)
    assert any("server.port" in e for e in errors)
    assert any("steam.username" in e for e in errors)
    assert any("paths.install_dir" in e for e in errors)


def test_port_must_be_int():
    cfg = _valid_config()
    cfg["server"]["port"] = "2302"  # string, não int
    errors = validate_config(cfg)

    assert any("server.port" in e and "inteiro" in e for e in errors)


def test_port_out_of_range():
    cfg = _valid_config()
    cfg["server"]["port"] = 70000  # acima de 65535
    errors = validate_config(cfg)

    assert any("server.port" in e for e in errors)


def test_retention_days_must_be_positive():
    cfg = _valid_config()
    cfg["backup"] = {"retention_days": 0}
    errors = validate_config(cfg)

    assert any("retention_days" in e for e in errors)
