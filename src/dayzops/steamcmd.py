import os
import re
import shutil
import subprocess
import sys

from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("steamcmd")

# App IDs (Valve / SteamDB).
DAYZ_SERVER_APPID = "223350"  # DayZ Dedicated Server (Linux)
DAYZ_APPID = "221100"         # DayZ (usado para baixar mods do Workshop)

# A senha do Steam é lida SÓ desta env var — nunca do server.yaml.
STEAM_PASSWORD_ENV = "DAYZOPS_STEAM_PASSWORD"

# O SteamCMD imprime o caminho real onde depositou o item do Workshop.
# Ex.: Success. Downloaded item 123 to "/srv/dayz/.steam/.../123" (N bytes)
_DOWNLOAD_PATH = re.compile(r'Downloaded item \d+ to "([^"]+)"')


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
        run_as: str | None = None,
    ):
        self.username = username
        self.steamcmd_path = steamcmd_path
        self.timeout = timeout
        # Usuário de serviço sob o qual o steamcmd deve rodar. Quando o DayZops
        # está como root, baixar como root joga o conteúdo do Workshop em
        # /root/.steam — ilegível pelo usuário de serviço. Rodando como esse
        # usuário, o conteúdo cai no HOME dele (ex.: /srv/dayz/.steam).
        self.run_as = run_as
        self._runner = runner or self._default_runner

    def is_available(self) -> bool:
        return shutil.which(self.steamcmd_path) is not None

    def _wrap_as_user(self, command: list[str]) -> list[str]:
        """Prefixa 'sudo -H -u <run_as>' quando estamos como root e há usuário.

        O -H ajusta HOME para o do usuário de serviço, o que é essencial: o
        SteamCMD procura credencial cacheada (sentryfile do Steam Guard) em
        $HOME/.steam. Sem -H, o HOME continua sendo /root e o login falha
        pedindo Guard novamente — sem TTY para digitar.
        """
        if self.run_as and hasattr(os, "geteuid") and os.geteuid() == 0:
            return ["sudo", "-H", "-u", self.run_as, *command]
        return command

    def _login_args(self) -> list[str]:
        password = os.environ.get(STEAM_PASSWORD_ENV)
        args = ["+login", self.username]
        if password:
            args.append(password)
        return args

    def build_command(self, steam_actions: list[str]) -> list[str]:
        """Monta a linha de comando completa (lista de args, sem shell)."""
        base = [self.steamcmd_path, *self._login_args(), *steam_actions, "+quit"]
        return self._wrap_as_user(base)

    def _redact(self, command: list[str]) -> list[str]:
        password = os.environ.get(STEAM_PASSWORD_ENV)
        if not password:
            return command
        return ["***" if part == password else part for part in command]

    def _default_runner(self, command: list[str]):
        """Roda o steamcmd repassando stdout/stderr em tempo real ao terminal.

        Capturar tudo com capture_output=True faz três coisas ruins: esconde a
        porcentagem do download (a operação parece 'travada'), tira o TTY
        (alguns prompts do SteamCMD só aparecem com terminal) e a saída só
        chega no fim. Aqui, fazemos line-buffering: cada linha vai ao terminal
        ao mesmo tempo que é guardada em memória para o _link_workshop_item
        (que precisa do caminho de download) e para a mensagem de erro.
        """
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        buf: list[str] = []
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                sys.stderr.write(line)
                sys.stderr.flush()
                buf.append(line)
            returncode = proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise
        return subprocess.CompletedProcess(
            args=command, returncode=returncode, stdout="".join(buf), stderr=""
        )

    def run(self, steam_actions: list[str]):
        command = self.build_command(steam_actions)
        log.info("steamcmd: %s", " ".join(self._redact(command)))
        result = self._runner(command)
        if result.returncode != 0:
            tail = (getattr(result, "stdout", "") or "")[-500:]
            raise SteamCmdError(
                f"steamcmd falhou (exit {result.returncode}).\nSaída final:\n{tail}"
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

    def download_mod(self, workshop_id, *, workshop_dir, validate: bool = True):
        """Baixa um mod do Workshop e o materializa em workshop_dir/<id>.

        O SteamCMD deposita o conteúdo no layout dele
        (<steam_root>/SteamApps/workshop/content/221100/<id>), que NÃO é o
        workshop_dir do DayZops. Lemos o caminho real da saída do SteamCMD e
        criamos um symlink workshop_dir/<id> -> caminho_real, deixando o
        conteúdo onde o resto do DayZops espera (ADR-0003) sem duplicar bytes
        e sem quebrar os updates incrementais do SteamCMD.
        """
        action = ["+workshop_download_item", DAYZ_APPID, str(workshop_id)]
        if validate:
            action.append("validate")
        result = self.run(action)
        self._link_workshop_item(workshop_id, Path(workshop_dir), result)
        return result

    def _link_workshop_item(self, workshop_id, workshop_dir: Path, result) -> None:
        target = workshop_dir / str(workshop_id)
        stdout = getattr(result, "stdout", "") or ""

        match = _DOWNLOAD_PATH.search(stdout)
        if not match:
            log.warning(
                "caminho de download do item %s não encontrado na saída do "
                "steamcmd; symlink não criado", workshop_id
            )
            return

        real_path = Path(match.group(1))
        workshop_dir.mkdir(parents=True, exist_ok=True)

        if target.is_symlink():
            if os.readlink(target) == str(real_path):
                return  # já aponta para o lugar certo
            target.unlink()
        elif target.exists():
            # Diretório real (ex.: movido à mão) — não sobrescrevemos.
            log.warning("%s existe e não é symlink; mantido", target)
            return

        target.symlink_to(real_path)
        log.info("workshop item %s -> %s", workshop_id, real_path)
