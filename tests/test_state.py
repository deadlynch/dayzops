import json

from dayzops.state import StateStore


def test_read_missing_returns_default(tmp_path):
    store = StateStore(tmp_path)
    assert store.read("nope.json", default=[]) == []
    assert store.installed_mods() == []
    assert store.last_backup() is None


def test_write_and_read_roundtrip(tmp_path):
    store = StateStore(tmp_path)
    store.set_installed_mods([{"id": 1559212036, "name": "CF"}])
    assert store.installed_mods() == [{"id": 1559212036, "name": "CF"}]


def test_write_leaves_no_tmp_file(tmp_path):
    store = StateStore(tmp_path)
    store.set_installed_keys(["cf.bikey"])
    assert list(tmp_path.glob("*.tmp")) == []


def test_record_backup_adds_timestamp(tmp_path):
    store = StateStore(tmp_path)
    store.record_backup(path="/srv/dayz/backups/2026.tar")

    rec = store.last_backup()
    assert "timestamp" in rec
    assert rec["path"] == "/srv/dayz/backups/2026.tar"


def test_inventory_consolidates_and_persists(tmp_path):
    store = StateStore(tmp_path)
    store.set_installed_mods([{"id": 1}])
    store.record_update(version="1.26")

    inv = store.write_inventory()
    assert inv["installed_mods"] == [{"id": 1}]
    assert inv["last_update"]["version"] == "1.26"
    assert "generated_at" in inv

    on_disk = json.loads((tmp_path / "inventory.json").read_text())
    assert on_disk["installed_mods"] == [{"id": 1}]
