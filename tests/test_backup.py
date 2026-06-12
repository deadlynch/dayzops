import io
import tarfile

import pytest

from dayzops.backup import BackupManager, BackupError, DEFAULT_SCOPE
from dayzops.state import StateStore


def _make_server(tmp_path):
    """Monta um install_dir falso com parte do escopo do ADR-0005."""
    server = tmp_path / "server"
    (server / "profiles").mkdir(parents=True)
    (server / "profiles" / "log.txt").write_text("dados do mundo")
    (server / "serverDZ.cfg").write_text("hostname = Test;")
    return server


def test_create_includes_existing_scope(tmp_path):
    server = _make_server(tmp_path)
    bm = BackupManager(server, tmp_path / "backups")

    archive = bm.create()
    assert archive.exists()

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "serverDZ.cfg" in names
    assert any(n.startswith("profiles") for n in names)


def test_create_records_state(tmp_path):
    server = _make_server(tmp_path)
    store = StateStore(tmp_path / "state")
    bm = BackupManager(server, tmp_path / "backups", store=store)

    bm.create()
    assert store.last_backup() is not None
    assert "serverDZ.cfg" in store.last_backup()["included"]


def test_create_aborts_when_scope_empty(tmp_path):
    empty = tmp_path / "empty-server"
    empty.mkdir()
    bm = BackupManager(empty, tmp_path / "backups")
    with pytest.raises(BackupError):
        bm.create()
    # nenhum .tmp órfão
    assert list((tmp_path / "backups").glob("*.tmp")) == []


def test_restore_roundtrip(tmp_path):
    server = _make_server(tmp_path)
    bm = BackupManager(server, tmp_path / "backups")
    bm.create()

    # simula perda de dados
    (server / "serverDZ.cfg").unlink()
    assert not (server / "serverDZ.cfg").exists()

    bm.restore()
    assert (server / "serverDZ.cfg").read_text() == "hostname = Test;"


def test_restore_without_backup_raises(tmp_path):
    server = _make_server(tmp_path)
    bm = BackupManager(server, tmp_path / "backups")
    with pytest.raises(BackupError):
        bm.restore()


def test_safe_extract_rejects_path_traversal(tmp_path):
    server = _make_server(tmp_path)
    backups = tmp_path / "backups"
    backups.mkdir()

    # arquivo malicioso com membro '../escapou'
    evil = backups / "dayz-backup-20990101T000000Z.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        data = b"boom"
        info = tarfile.TarInfo(name="../escapou")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    bm = BackupManager(server, backups)
    with pytest.raises(BackupError):
        bm.restore(evil)
    # confirma que NADA escapou para fora do server_dir
    assert not (tmp_path / "escapou").exists()


def test_default_scope_matches_adr(tmp_path):
    # Trava o escopo documentado no ADR-0005.
    assert DEFAULT_SCOPE == [
        "profiles", "mpmissions", "battleye", "config", "custom", "serverDZ.cfg",
    ]
