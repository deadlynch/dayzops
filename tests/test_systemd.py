import types

import pytest

from dayzops.systemd import (
    ServerControl,
    SystemdError,
    SERVER_SERVICE,
    render_server_unit,
    render_update_timer,
    generate_units,
)


def _result(returncode=0, stdout=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def test_server_unit_contains_exec_and_restart():
    unit = render_server_unit(exec_start="/srv/dayz/server/DayZServer -config=x.cfg",
                              working_dir="/srv/dayz/server")
    assert "ExecStart=/srv/dayz/server/DayZServer" in unit
    assert "Restart=on-failure" in unit
    assert "[Install]" in unit


def test_timer_maps_schedule_to_oncalendar():
    timer = render_update_timer(schedule="04:00")
    assert "OnCalendar=*-*-* 04:00:00" in timer


def test_generate_units_writes_all_files(tmp_path):
    written = generate_units(
        tmp_path,
        exec_start="/srv/dayz/server/DayZServer",
        working_dir="/srv/dayz/server",
        schedule="03:30",
        prune_schedule="05:15",
    )
    assert set(written.keys()) == {
        "dayz.service", "dayz-update.service", "dayz-update.timer",
        "dayz-prune.service", "dayz-prune.timer",
    }
    assert (tmp_path / "dayz.service").exists()
    assert "03:30:00" in (tmp_path / "dayz-update.timer").read_text()
    assert "05:15:00" in (tmp_path / "dayz-prune.timer").read_text()


def test_start_builds_correct_command():
    captured = {}

    def runner(cmd):
        captured["cmd"] = cmd
        return _result(0)

    ServerControl(runner=runner, use_sudo=True).start()
    assert captured["cmd"] == ["sudo", "systemctl", "start", SERVER_SERVICE]


def test_no_sudo_when_disabled():
    captured = {}
    ServerControl(runner=lambda c: (captured.setdefault("cmd", c), _result(0))[1],
                  use_sudo=False).stop()
    assert captured["cmd"] == ["systemctl", "stop", SERVER_SERVICE]


def test_failure_raises():
    sc = ServerControl(runner=lambda c: _result(1), use_sudo=False)
    with pytest.raises(SystemdError):
        sc.start()


def test_is_active_parses_output():
    active = ServerControl(runner=lambda c: _result(0, "active\n"), use_sudo=False)
    inactive = ServerControl(runner=lambda c: _result(3, "inactive\n"), use_sudo=False)
    assert active.is_active() is True
    assert inactive.is_active() is False
