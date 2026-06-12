import os
import time
import types

from dayzops import app


def _svc(tmp_path, retention_days=14):
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
        "mods": [], "backup": {"retention_days": retention_days},
    }
    return app.build_services(cfg)


def test_prune_removes_old_keeps_recent(tmp_path):
    svc = _svc(tmp_path, retention_days=14)
    recent = svc.backup.create()

    # fabrica um backup antigo com nome distinto e mtime de 30 dias atrás
    old = svc.backup.backups_dir / "dayz-backup-20200101T000000Z.tar.gz"
    old.write_bytes(b"old")
    old_time = time.time() - 30 * 86400
    os.utime(old, (old_time, old_time))

    removed = app.do_prune(svc)
    assert old in removed
    assert not old.exists()
    assert recent.exists()


def test_prune_nothing_when_all_recent(tmp_path):
    svc = _svc(tmp_path)
    svc.backup.create()
    assert app.do_prune(svc) == []
