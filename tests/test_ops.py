import pytest

from dayzops.lock import global_lock, LockError
from dayzops.ops import UpdatePlan, run_update, UpdateError
from dayzops.state import StateStore


def _recording_plan(calls, *, fail_validate=False):
    def step(name):
        def _fn(*args, **kwargs):
            calls.append(name)
            if name == "validate" and fail_validate:
                raise RuntimeError("validação quebrou")
        return _fn

    return UpdatePlan(
        update_server=step("update_server"),
        create_backup=step("create_backup"),
        restore_backup=step("restore_backup"),
        stop_server=step("stop_server"),
        update_mods=step("update_mods"),
        validate=step("validate"),
        sync_keys=step("sync_keys"),
        start_server=step("start_server"),
        health_check=step("health_check"),
    )


def test_happy_path_runs_steps_in_order(tmp_path):
    calls = []
    run_update(
        _recording_plan(calls),
        store=StateStore(tmp_path),
        lock_file=tmp_path / "dayzops.lock",
    )
    assert calls == [
        "create_backup", "stop_server", "update_server", "update_mods",
        "validate", "sync_keys", "start_server", "health_check",
    ]


def test_success_records_state(tmp_path):
    store = StateStore(tmp_path)
    run_update(
        _recording_plan([]),
        store=store,
        lock_file=tmp_path / "dayzops.lock",
    )
    assert store.last_update()["status"] == "success"
    assert (tmp_path / "inventory.json").exists()


def test_validation_failure_triggers_rollback(tmp_path):
    calls = []
    store = StateStore(tmp_path)

    with pytest.raises(UpdateError):
        run_update(
            _recording_plan(calls, fail_validate=True),
            store=store,
            lock_file=tmp_path / "dayzops.lock",
        )

    # Restaura backup DEPOIS da validação falhar...
    assert calls.index("restore_backup") > calls.index("validate")
    # ...passos posteriores não rodam...
    assert "sync_keys" not in calls
    assert "health_check" not in calls
    # ...e nenhum update bem-sucedido foi gravado.
    assert store.last_update() is None


def test_lock_held_during_update(tmp_path):
    lock_file = tmp_path / "dayzops.lock"
    calls = []

    def step(name):
        def _fn(*args, **kwargs):
            calls.append(name)
            if name == "update_server":
                # Outra operação tentando o lock agora deve abortar.
                with pytest.raises(LockError):
                    with global_lock(lock_file):
                        pass
        return _fn

    plan = UpdatePlan(
        update_server=step("update_server"),
        create_backup=step("create_backup"),
        restore_backup=step("restore_backup"),
        stop_server=step("stop_server"),
        update_mods=step("update_mods"),
        validate=step("validate"),
        sync_keys=step("sync_keys"),
        start_server=step("start_server"),
        health_check=step("health_check"),
    )
    run_update(plan, store=StateStore(tmp_path), lock_file=lock_file)
    assert "update_server" in calls


def test_runs_with_only_update_server_using_stubs(tmp_path):
    # Só o passo real implementado; o resto cai nos stubs e não quebra.
    calls = []
    plan = UpdatePlan(update_server=lambda *a, **k: calls.append("update_server"))
    run_update(plan, store=StateStore(tmp_path), lock_file=tmp_path / "dayzops.lock")
    assert calls == ["update_server"]
