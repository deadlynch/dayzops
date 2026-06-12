import os
import shutil
import subprocess

from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("steamcmd")

# App IDs (Valve / SteamDB).
DAYZ_SERVER_APPID = "223350"  # DayZ Dedicated Server (Linux)
DAYZ_APPID = "221100"         # DayZ (usado para baixar mods do Workshop)

# A senha do Steam é lida SÓ desta env var — nunca do server.yaml.
# Manter segredo fora do arquivo de config declarativo é regra: o YAML é
# versionável/compartilhável, a senha não.
STEAM_PASSWORD_ENV = "DAYZOPS_STEAM_PASSWORD"
STEAM_PASSWORD_FILE = Path("/etc/dayzops.env")


class SteamCmdError(Exception):
    pass


class SteamCmd:
    """Invólucro fino sobre o binário steamcmd.

    A lógica de montar o comando (pura, testável) fica separada da execução
    do subprocesso (efeito colateral), o que deixa o módulo testável sem ter
    o steamcmd instalado: nos testes injeta-se um `runner` falso.
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
        # Injeção de dependência: o teste passa um runner falso.
        self._runner = runner or self._default_runner

    def is_available(self) -> bool:
        """True se o binário steamcmd está no PATH (ou no caminho dado)."""
        return shutil.which(self.steamcmd_path) is not None

    def _password(self) -> str | None:
        password = os.environ.get(STEAM_PASSWORD_ENV)
        if password:
            return password
        return self._read_password_file()

    def _read_password_file(self) -> str | None:
        try:
            text = STEAM_PASSWORD_FILE.read_text(encoding="utf-8")
        except OSError:
            return None

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != STEAM_PASSWORD_ENV:
                continue
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in ("'", '"')
            ):
                value = value[1:-1]
            return value
        return None

    def _login_args(self) -> list[str]:
        password = self._password()
        args = ["+login", self.username]
        if password:
            # Sem senha, o steamcmd usa credencial em cache ou pede interativo.
            args.append(password)
        return args

    def build_command(self, steam_actions: list[str]) -> list[str]:
        """Monta a linha de comando completa (lista de args, sem shell)."""
        return [
            self.steamcmd_path,
            *self._login_args(),
            *steam_actions,
            "+quit",
        ]

    def _redact(self, command: list[str]) -> list[str]:
        """Versão do comando segura para log: troca a senha por ***."""
        password = self._password()
        if not password:
            return command
        return ["***" if part == password else part for part in command]

    def _default_runner(self, command: list[str]):
        # Lista de args (sem shell=True) evita injeção de shell.
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )

    def run(self, steam_actions: list[str]):
        command = self.build_command(steam_actions)
        # Loga a versão redigida — a senha NUNCA vai pro log.
        log.info("steamcmd: %s", " ".join(self._redact(command)))

        result = self._runner(command)

        if result.returncode != 0:
            tail = (getattr(result, "stdout", "") or "")[-500:]
            raise SteamCmdError(
                f"steamcmd falhou (exit {result.returncode}).\n"
                f"Saída final:\n{tail}"
            )
        return result

    # --- Operações de alto nível ---

    def install_or_update_server(self, install_dir: Path):
        """Instala OU atualiza o servidor (no steamcmd é o mesmo comando)."""
        return self.run(
            [
                "+force_install_dir", str(install_dir),
                "+app_update", DAYZ_SERVER_APPID, "validate",
            ]
        )

    def download_mod(self, workshop_id, *, validate: bool = True):
        """Baixa/atualiza um mod do Workshop (sob o appid do jogo)."""
        action = ["+workshop_download_item", DAYZ_APPID, str(workshop_id)]
        if validate:
            action.append("validate")
        return self.run(action)
