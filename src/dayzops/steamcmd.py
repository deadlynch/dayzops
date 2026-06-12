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
    """
    Wrapper estável do SteamCMD.

    REGRA PRINCIPAL:
    - SteamCMD sempre recebe um único comando linear
    - ordem dos parâmetros é responsabilidade do caller
    """

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
    # login (EXPLOÍCITO)
    # -------------------------

    def login_args(self) -> list[str]:
        """
        Nunca injeta login automaticamente.
        Caller decide se usa anonymous ou account real.
        """
        password = os.environ.get(STEAM_PASSWORD_ENV)

        if self.username and password:
            return ["+login", self.username, password]

        return ["+login", "anonymous"]

    # -------------------------
    # execução
    # -------------------------

    def run(self, steam_actions: list[str]):
        """
        Executa SteamCMD com comando já montado corretamente.
        """

        command = [self.steamcmd_path, *steam_actions, "+quit"]

        log.info("steamcmd: %s", " ".join(command))

        result = self._runner(command)

        if result.returncode != 0:
            tail = (result.stdout or "")[-1000:]
            raise SteamCmdError(
                f"steamcmd falhou (exit {result.returncode}).\n"
                f"Saída final:\n{tail}"
            )

        return result

    # -------------------------
    # operações
    # -------------------------

    def install_or_update_server(self, install_dir: Path):
        """
        ORDEM CORRETA (OBRIGATÓRIA):
        force_install_dir -> login -> app_update
        """

        return self.run([
            "+force_install_dir", str(install_dir),
            *self.login_args(),
            "+app_update", DAYZ_SERVER_APPID, "validate",
        ])

    def download_mod(self, workshop_id: str, *, validate: bool = True):
        """
        Workshop usa appid do DayZ (221100)
        """

        cmd = [
            *self.login_args(),
            "+workshop_download_item", DAYZ_APPID, str(workshop_id),
        ]

        if validate:
            cmd.append("validate")

        return self.run(cmd)
