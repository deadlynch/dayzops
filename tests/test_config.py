from dayzops.config import validate_config


def test_valid_config():
    cfg = {
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

    assert validate_config(cfg) == []