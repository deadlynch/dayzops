import os
import shutil
import subprocess
from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("steamcmd")

DAYZ_SERVER_APPID = "223350"
DAYZ_APPID = "221100"

STEAM_PASSWORD_ENV = "DAYZOPS_STEAM_PASSWORD"


class SteamCmdError(Exception):
    pass


class SteamCmd:
    def __init__(
        self,
        username: str,
        *,
        steamcmd_path: str = "steamcmd",
        timeout: int = 1800,
        runner=None,
    ):
        self.username = username
        self.steamcmd_path = steamcmd_path
        self.timeout = timeout
        self._runner = runner or self._default_runner

    # -------------------------
    # infra
    # -------------------------

    def is_available(self) -> bool:
        return shutil.which(self.steamcmd_path) is not None

    def _default_runner(self, command: list[str]):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )

    # -------------------------
    # login
    # -------------------------

    def _login_args(self) -> list[str]:
        """
        SteamCMD rules:
        +login user password
        OR
        +login anonymous
        """
        password = os.environ.get(STEAM_PASSWORD_ENV)

        if self.username and password:
            return ["+login", self.username, password]

        # fallback seguro
        return ["+login", "anonymous"]

    # -------------------------
    # command builder (FIX PRINCIPAL)
    # -------------------------

    def build_command(self, steam_actions: list[str]) -> list[str]:
        """
        Ordem correta SEMPRE:
        steamcmd +force_install_dir +login +app_update +quit
        """
        return [
            self.steamcmd_path,
            *steam_actions,
            "+quit",
        ]

    def _redact(self, command: list[str]) -> list[str]:
        password = os.environ.get(STEAM_PASSWORD_ENV)
        if not password:
            return command
        return ["***" if part == password else part for part in command]

    def run(self, steam_actions: list[str]):
        command = self.build_command(steam_actions)

        log.info("steamcmd: %s", " ".join(self._redact(command)))

        result = self._runner(command)

        if result.returncode != 0:
            tail = (result.stdout or "")[-800:]
            raise SteamCmdError(
                f"steamcmd falhou (exit {result.returncode}).\n"
                f"Saída final:\n{tail}"
            )

        return result

    # -------------------------
    # high level ops
    # -------------------------

    def install_or_update_server(self, install_dir: Path):
        """
        CORRETO:
        force_install_dir SEMPRE antes do login
        """
        return self.run([
            "+force_install_dir", str(install_dir),
            *self._login_args(),
            "+app_update", DAYZ_SERVER_APPID, "validate",
        ])

    def download_mod(self, workshop_id: str, *, validate: bool = True):
        """
        Workshop usa appid do DayZ (221100)
        """
        actions = [
            "+workshop_download_item", DAYZ_APPID, str(workshop_id),
        ]

        if validate:
            actions.append("validate")

        return self.run([
            *self._login_args(),
            *actions,
        ])
