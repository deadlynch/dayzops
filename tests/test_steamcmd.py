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
    # Sem a env var: só "+login alice", sem terceiro elemento de senha.
    # (O steamcmd usa credencial em cache ou pede interativo.)
    login_idx = cmd.index("+login")
    assert cmd[login_idx + 1] == "alice"
    assert len(cmd) == login_idx + 2 + 1  # +login, alice, +quit


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


def test_download_mod_uses_game_appid(monkeypatch, tmp_path):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    captured = {}

    real = tmp_path / "steamroot" / "1559212036"
    real.mkdir(parents=True)

    def runner(cmd):
        captured["cmd"] = cmd
        return _fake_result(0, f'Success. Downloaded item 1559212036 to "{real}" (5 bytes)')

    sc = SteamCmd("alice", runner=runner)
    workshop = tmp_path / "workshop"
    sc.download_mod(1559212036, workshop_dir=workshop)

    cmd = captured["cmd"]
    assert "+workshop_download_item" in cmd
    assert DAYZ_APPID in cmd
    assert "1559212036" in cmd
    assert "validate" in cmd

    # materializou: workshop/<id> é symlink para o caminho real do steamcmd
    link = workshop / "1559212036"
    assert link.is_symlink()
    assert link.resolve() == real.resolve()


def test_download_mod_handles_missing_path(monkeypatch, tmp_path):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    # saída sem a linha "Downloaded item ... to" -> não cria symlink, não quebra
    sc = SteamCmd("alice", runner=lambda c: _fake_result(0, "sem caminho aqui"))
    workshop = tmp_path / "workshop"
    sc.download_mod(42, workshop_dir=workshop)
    assert not (workshop / "42").exists()
