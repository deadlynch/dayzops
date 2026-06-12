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


def test_runs_as_service_user_when_root(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    monkeypatch.setattr("dayzops.steamcmd.os.geteuid", lambda: 0)  # finge root
    sc = SteamCmd("alice", run_as="dayz")
    cmd = sc.build_command(["+app_update", "223350"])
    # sudo -H --preserve-env=DAYZOPS_STEAM_PASSWORD -u dayz steamcmd ...
    assert cmd[0] == "sudo"
    assert "-H" in cmd[:5]
    assert "-u" in cmd and cmd[cmd.index("-u") + 1] == "dayz"
    assert "steamcmd" in cmd


def test_no_sudo_wrap_when_not_root(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    monkeypatch.setattr("dayzops.steamcmd.os.geteuid", lambda: 1000)  # não-root
    sc = SteamCmd("alice", run_as="dayz")
    cmd = sc.build_command(["+app_update", "223350"])
    assert "sudo" not in cmd
    assert cmd[0] == "steamcmd"


def test_no_sudo_wrap_without_run_as(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    monkeypatch.setattr("dayzops.steamcmd.os.geteuid", lambda: 0)
    sc = SteamCmd("alice")  # sem run_as
    cmd = sc.build_command([])
    assert "sudo" not in cmd


def test_reads_password_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    env = tmp_path / "dayzops.env"
    env.write_text("# comentário\nDAYZOPS_STEAM_PASSWORD=fromfile\n")
    monkeypatch.setattr("dayzops.steamcmd.ENV_FILE_PATH", str(env))

    sc = SteamCmd("alice")
    cmd = sc.build_command([])
    assert "fromfile" in cmd
    # E o redact some com ela.
    assert "fromfile" not in sc._redact(cmd)


def test_env_var_wins_over_env_file(monkeypatch, tmp_path):
    env = tmp_path / "dayzops.env"
    env.write_text("DAYZOPS_STEAM_PASSWORD=fromfile\n")
    monkeypatch.setattr("dayzops.steamcmd.ENV_FILE_PATH", str(env))
    monkeypatch.setenv(STEAM_PASSWORD_ENV, "fromenv")

    sc = SteamCmd("alice")
    cmd = sc.build_command([])
    assert "fromenv" in cmd
    assert "fromfile" not in cmd


def test_sudo_wrap_preserves_password_env(monkeypatch):
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    monkeypatch.setattr("dayzops.steamcmd.os.geteuid", lambda: 0)
    sc = SteamCmd("alice", run_as="dayz")
    cmd = sc.build_command([])
    # Sem o --preserve-env, sudo filtra DAYZOPS_STEAM_PASSWORD ao trocar de
    # usuário e o steamcmd cai em prompt -> Invalid Password.
    assert f"--preserve-env={STEAM_PASSWORD_ENV}" in cmd


def test_invalid_password_without_credential_raises_actionable(monkeypatch):
    from dayzops.steamcmd import SteamAuthError
    monkeypatch.delenv(STEAM_PASSWORD_ENV, raising=False)
    monkeypatch.setattr("dayzops.steamcmd.ENV_FILE_PATH", "/no/such/file")

    def runner(cmd):
        return _fake_result(5, "Logging in user 'alice'...ERROR (Invalid Password)")

    sc = SteamCmd("alice", runner=runner)
    try:
        sc.run([])
    except SteamAuthError as exc:
        assert "senha não configurada" in str(exc)
        return
    raise AssertionError("deveria ter levantado SteamAuthError")


def test_invalid_password_with_credential_suggests_steam_login(monkeypatch):
    from dayzops.steamcmd import SteamAuthError
    monkeypatch.setenv(STEAM_PASSWORD_ENV, "secret")

    def runner(cmd):
        return _fake_result(5, "Logging in user 'alice'...ERROR (Invalid Password)")

    sc = SteamCmd("alice", runner=runner)
    try:
        sc.run([])
    except SteamAuthError as exc:
        assert "steam-login" in str(exc)
        return
    raise AssertionError("deveria ter levantado SteamAuthError")
