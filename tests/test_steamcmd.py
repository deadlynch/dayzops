import types

import pytest

from dayzops.steamcmd import (
    SteamCmd,
    SteamCmdError,
    DAYZ_SERVER_APPID,
    DAYZ_APPID,
    STEAM_PASSWORD_ENV,
)


def _fake_result(returncode=0, stdout=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def test_build_command_structure():
    sc = SteamCmd("alice")
    cmd = sc.build_command(["+app_update", DAYZ_SERVER_APPID])

    assert cmd[0] == "steamcmd"
    assert "+login" in cmd and "alice" in cmd
    assert cmd[-1] == "+quit"


def test_password_comes_from_env_not_config(monkeypatch):
    monkeypatch.setenv(STEAM_PASSWORD_ENV, "s3cret")
    sc = SteamCmd("alice")
    cmd = sc.build_command([])

    # A senha entra no comando real...
    assert "s3cret" in cmd
    # ...mas a versão para log é redigida.
    assert "s3cret" not in sc._redact(cmd)
    assert "***" in sc._redact(cmd)


def test_no_password_when_env_absent(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    sc = SteamCmd("alice")
    cmd = sc.build_command([])
    # Só "+login alice", sem terceiro elemento de senha.
    login_idx = cmd.index("+login")
    assert cmd[login_idx + 1] == "alice"


def test_nonzero_exit_raises(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    sc = SteamCmd("alice", runner=lambda cmd: _fake_result(1, "erro de rede"))
    with pytest.raises(SteamCmdError) as exc:
        sc.run(["+app_update", DAYZ_SERVER_APPID])
    assert "erro de rede" in str(exc.value)


def test_success_returns_result(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    sc = SteamCmd("alice", runner=lambda cmd: _fake_result(0, "Success"))
    result = sc.install_or_update_server("/srv/dayz/server")
    assert result.returncode == 0


def test_download_mod_uses_game_appid(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    captured = {}

    def runner(cmd):
        captured["cmd"] = cmd
        return _fake_result(0)

    sc = SteamCmd("alice", runner=runner)
    sc.download_mod(1559212036)

    cmd = captured["cmd"]
    assert "+workshop_download_item" in cmd
    assert DAYZ_APPID in cmd
    assert "1559212036" in cmd
    assert "validate" in cmd
