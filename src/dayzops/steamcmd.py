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

# Arquivo de ambiente lido como fallback (mesmo que o systemd usa via
# EnvironmentFile). Permite que o CLI manual ('sudo dayzops apply') funcione
# sem precisar exportar a env var nem confiar no 'sudo --preserve-env' —
# importante porque o nosso wrap 'sudo -H -u dayz' troca de usuário e o
# ambiente do invocador é filtrado por padrão.
ENV_FILE_PATH = "/etc/dayzops.env"

# O SteamCMD imprime o caminho real onde depositou o item do Workshop.
# Ex.: Success. Downloaded item 123 to "/srv/dayz/.steam/.../123" (N bytes)
_DOWNLOAD_PATH = re.compile(r'Downloaded item \d+ to "([^"]+)"')


def _read_password_from_env_file(path: str | None = None) -> str | None:
    """Lê DAYZOPS_STEAM_PASSWORD de um EnvironmentFile (formato 'KEY=value').

    Silencioso: se o arquivo não existe ou não tem a chave, devolve None.
    Linhas começando com '#' são comentários; aspas opcionais são removidas.
    """
    if path is None:
        path = ENV_FILE_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == STEAM_PASSWORD_ENV:
                    value = value.strip().strip('"').strip("'")
                    return value or None
    except OSError:
        return None
    return None


def _resolve_password() -> str | None:
    """Senha da env var (preferida) com fallback para o EnvironmentFile."""
    return os.environ.get(STEAM_PASSWORD_ENV) or _read_password_from_env_file()


class SteamCmdError(Exception):
    pass


class SteamAuthError(SteamCmdError):
    """SteamCMD recusou login — credencial ausente, errada, ou Guard exigido.

    Mensagem é acionável (diz o que fazer), não stacktrace cru.
    """


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
        """Prefixa 'sudo -H --preserve-env=... -u <run_as>' quando root.

        - -H ajusta HOME para o do usuário de serviço (essencial: SteamCMD
          procura credencial cacheada em $HOME/.steam).
        - --preserve-env preserva DAYZOPS_STEAM_PASSWORD através da troca de
          usuário (sudo filtra o ambiente por padrão; sem isso, a senha não
          chega ao SteamCMD e ele cai em prompt interativo / Invalid Password).
        """
        if self.run_as and hasattr(os, "geteuid") and os.geteuid() == 0:
            return [
                "sudo", "-H",
                f"--preserve-env={STEAM_PASSWORD_ENV}",
                "-u", self.run_as,
                *command,
            ]
        return command

    def _login_args(self) -> list[str]:
        password = _resolve_password()
        args = ["+login", self.username]
        if password:
            args.append(password)
        return args

    def build_command(self, steam_actions: list[str]) -> list[str]:
        """Monta a linha de comando completa (lista de args, sem shell)."""
        base = [self.steamcmd_path, *self._login_args(), *steam_actions, "+quit"]
        return self._wrap_as_user(base)

    def _redact(self, command: list[str]) -> list[str]:
        password = _resolve_password()
        if not password:
            return command
        return ["***" if part == password else part for part in command]

    def _default_runner(self, command: list[str]):
        """Roda o steamcmd repassando stdout/stderr em tempo real ao terminal.

        - O env é construído a partir do atual + a senha resolvida. Quando o
          comando é prefixado com 'sudo -H -u dayz', o sudo filtra o ambiente
          por padrão, então NÃO basta a senha estar no os.environ do pai;
          ela tem que ir explicitamente no env do Popen, e o sudo é instruído
          a preservá-la via --preserve-env (acrescentado no _wrap_as_user).
        - stdin herda o terminal pai: na primeira execução sem cache, o
          operador pode digitar Steam Guard (interativo). Sob timer/serviço
          sem TTY, simplesmente falha com mensagem acionável.
        - stdout/stderr saem em tempo real (vê a porcentagem) e são gravados
          em buffer para _link_workshop_item e para mensagens de erro.
        """
        env = os.environ.copy()
        password = _resolve_password()
        if password:
            env[STEAM_PASSWORD_ENV] = password
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
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

    def interactive_login(self) -> int:
        """Executa 'steamcmd +login <user> +quit' com stdio totalmente herdado.

        Modo 'steam-login': o operador roda uma vez por máquina/conta para
        digitar Steam Guard (se aplicável) e popular o ssfn em $HOME/.steam
        do usuário de serviço. Independente do default_runner — aqui não
        capturamos saída para que o prompt do Guard apareça normalmente.
        """
        command = self._wrap_as_user(
            [self.steamcmd_path, *self._login_args(), "+quit"]
        )
        log.info("steam-login: %s", " ".join(self._redact(command)))
        env = os.environ.copy()
        password = _resolve_password()
        if password:
            env[STEAM_PASSWORD_ENV] = password
        return subprocess.call(command, env=env)

    def run(self, steam_actions: list[str]):
        command = self.build_command(steam_actions)
        log.info("steamcmd: %s", " ".join(self._redact(command)))
        result = self._runner(command)
        if result.returncode != 0:
            output = getattr(result, "stdout", "") or ""
            tail = output[-500:]
            # Falha de autenticação tem causas distintas: senha ausente
            # (env+arquivo vazios), senha errada, ou Guard exigido. Cada uma
            # tem ação diferente — o operador não deve precisar do stacktrace.
            if "Invalid Password" in output or "Login Failure" in output:
                if not _resolve_password():
                    raise SteamAuthError(
                        f"SteamCMD: senha não configurada para '{self.username}'. "
                        f"Defina DAYZOPS_STEAM_PASSWORD em {ENV_FILE_PATH} "
                        f"(uma linha: DAYZOPS_STEAM_PASSWORD=suasenha) "
                        f"ou exporte a variável de ambiente antes de rodar."
                    )
                raise SteamAuthError(
                    f"SteamCMD: credencial recusada para '{self.username}'. "
                    f"Se a conta usa Steam Guard, rode uma vez: "
                    f"sudo dayzops steam-login (para cachear o Guard). "
                    f"Caso contrário, confira usuário/senha em {ENV_FILE_PATH}."
                )
            if "Steam Guard" in output or "two-factor" in output.lower():
                raise SteamAuthError(
                    "SteamCMD: a conta exige Steam Guard. Rode uma vez "
                    "(interativo): sudo dayzops steam-login"
                )
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
