import os
import re
import shutil
import subprocess
import sys

from pathlib import Path

from dayzops.fsperm import chown_path, chown_recursive
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

# Caminhos onde o binário do SteamCMD costuma estar, em ordem de preferência.
# O DayZops instala via tarball oficial em <DAYZ_HOME>/steamcmd/steamcmd.sh,
# então esse é o primeiro candidato. NUNCA confiar só no nome "steamcmd" no
# PATH: sob 'sudo -u dayz' o secure_path filtra o ambiente e o comando some.
DEFAULT_STEAMCMD_PATHS = (
    "/srv/dayz/steamcmd/steamcmd.sh",   # instalação padrão do dayzops
    "/usr/games/steamcmd",              # pacote apt (Debian/Ubuntu, multiverse)
    "steamcmd",                         # último recurso: resolver pelo PATH
)


def _default_steamcmd_path() -> str:
    """Primeiro caminho de SteamCMD existente/resolvível.

    Para candidatos com '/', exige que o arquivo exista; para um nome simples,
    resolve via PATH. Se nada for encontrado, devolve o último (nome cru) para
    preservar a mensagem de erro histórica em vez de estourar aqui.
    """
    for cand in DEFAULT_STEAMCMD_PATHS:
        if "/" in cand:
            if Path(cand).is_file():
                return cand
        elif shutil.which(cand):
            return cand
    return DEFAULT_STEAMCMD_PATHS[-1]


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


def _clock_sync_state() -> bool | None:
    """Estado de sincronia NTP via timedatectl. True/False, ou None se indeterminado.

    Best-effort: se timedatectl não existe ou a saída é inesperada, devolve
    None (não bloqueia). Só devolve False quando há evidência clara de
    'System clock synchronized: no'.
    """
    if not shutil.which("timedatectl"):
        return None
    try:
        out = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return None
    if out in ("yes", "true", "1"):
        return True
    if out in ("no", "false", "0"):
        return False
    return None


class SteamCmdError(Exception):
    pass


class SteamAuthError(SteamCmdError):
    """SteamCMD recusou login — credencial ausente, errada, ou Guard exigido.

    Mensagem é acionável (diz o que fazer), não stacktrace cru.
    """


class SteamPreflightError(SteamCmdError):
    """Checagem prévia falhou ANTES de invocar o SteamCMD.

    Pega problemas previsíveis (binário ausente, senha não configurada,
    relógio fora de sincronia) e aborta com instrução clara, em vez de deixar
    o SteamCMD pendurar num prompt interativo ou estourar genérico.
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
        steamcmd_path: str | None = None,
        timeout: int = 1800,
        runner=None,
        run_as: str | None = None,
    ):
        self.username = username
        # steamcmd_path=None => auto-detecta o caminho absoluto do binário.
        # Passar um valor explícito (ex.: vindo de paths.steamcmd_bin no
        # server.yaml) tem precedência. Nunca cai no nome cru "steamcmd"
        # a menos que nenhum caminho conhecido exista.
        self.steamcmd_path = steamcmd_path or _default_steamcmd_path()
        self.timeout = timeout
        # Usuário de serviço sob o qual o steamcmd deve rodar. Quando o DayZops
        # está como root, baixar como root joga o conteúdo do Workshop em
        # /root/.steam — ilegível pelo usuário de serviço. Rodando como esse
        # usuário, o conteúdo cai no HOME dele (ex.: /srv/dayz/.steam).
        self.run_as = run_as
        self._runner = runner or self._default_runner

    def is_available(self) -> bool:
        # Caminho absoluto: basta o arquivo existir. Nome simples: via PATH.
        if "/" in self.steamcmd_path:
            return Path(self.steamcmd_path).is_file()
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
        """Redige credenciais para o log: a senha e o usuário do +login.

        A senha é trocada por '***' onde quer que apareça. O usuário não é um
        valor fixo conhecido aqui de forma segura (pode coincidir com outros
        args), então redigimos posicionalmente: o argumento imediatamente após
        '+login' é sempre o username.
        """
        password = _resolve_password()
        out: list[str] = []
        redact_next = False
        for part in command:
            if redact_next:
                out.append("***")
                redact_next = False
                continue
            if part == "+login":
                out.append(part)
                redact_next = True          # o próximo arg é o username
            elif password and part == password:
                out.append("***")
            else:
                out.append(part)
        return out

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
        # stdin fechado: sob apply/update/timer NÃO há ninguém para digitar
        # senha ou Steam Guard. Sem TTY, o SteamCMD falha imediatamente com
        # mensagem (capturada e traduzida em run()) em vez de pendurar à espera
        # de input — que era o caso do prompt travado com setas (^[[A). O login
        # interativo de verdade vive em interactive_login(), que herda o stdin.
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
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
        self.preflight(require_password=False)
        command = self._wrap_as_user(
            [self.steamcmd_path, *self._login_args(), "+quit"]
        )
        log.info("steam-login: %s", " ".join(self._redact(command)))
        env = os.environ.copy()
        password = _resolve_password()
        if password:
            env[STEAM_PASSWORD_ENV] = password
        return subprocess.call(command, env=env)

    def preflight(self, *, require_password: bool = True) -> None:
        """Valida o que dá pra validar ANTES de invocar o SteamCMD.

        Aborta com SteamPreflightError (mensagem acionável) quando:
          - o binário do SteamCMD não existe / não é executável;
          - a senha não está configurada (env nem EnvironmentFile) e é exigida;
          - o relógio do sistema está fora de sincronia (NTP), o que faz o
            handshake do Steam falhar de forma confusa.

        Não toca a rede nem a conta — é barato e idempotente. Chamar no início
        de apply/update/login evita falhas tardias e prompts pendurados.
        """
        # binário
        if not self.is_available():
            raise SteamPreflightError(
                f"SteamCMD não encontrado em '{self.steamcmd_path}'. "
                f"Rode o instalador (scripts/install.sh) ou ajuste "
                f"paths.steamcmd_bin no server.yaml."
            )
        # senha
        if require_password and not _resolve_password():
            raise SteamPreflightError(
                f"Senha do Steam não configurada para '{self.username}'. "
                f"Edite {ENV_FILE_PATH} e descomente a linha "
                f"'{STEAM_PASSWORD_ENV}=suasenha' (sem '#' na frente), "
                f"ou exporte a variável antes de rodar."
            )
        # relógio (best-effort; só avisa se claramente dessincronizado)
        skew = _clock_sync_state()
        if skew is False:
            log.warning(
                "relógio do sistema parece fora de sincronia (NTP). Se o login "
                "falhar, rode: sudo timedatectl set-ntp true"
            )

    def run(self, steam_actions: list[str]):
        self.preflight()
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
            low = output.lower()
            if "rate limit" in low or "too many" in low:
                raise SteamAuthError(
                    "SteamCMD: limite de tentativas atingido (rate limit). "
                    "O Steam bloqueia temporariamente após várias falhas de "
                    "login. Espere ~30 min e confira a senha em "
                    f"{ENV_FILE_PATH} antes de tentar de novo."
                )
            if "no subscription" in low:
                raise SteamCmdError(
                    f"SteamCMD: a conta '{self.username}' não possui o DayZ. "
                    f"O servidor (app {DAYZ_SERVER_APPID}) exige uma conta que "
                    f"seja dona do jogo — login anônimo não funciona."
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
        chown_path(workshop_dir, self.run_as)

        if target.is_symlink():
            if os.readlink(target) == str(real_path):
                return  # já aponta para o lugar certo
            target.unlink()
        elif target.exists():
            # Diretório real (ex.: movido à mão) — não sobrescrevemos.
            log.warning("%s existe e não é symlink; mantido", target)
            return

        target.symlink_to(real_path)
        chown_path(target, self.run_as)
        # Conteúdo real do mod (pode ter sido baixado como root se o
        # steamcmd rodou sem o sudo -u wrap) — garante dayz:dayz.
        if real_path.exists():
            chown_recursive(real_path, self.run_as)
        log.info("workshop item %s -> %s", workshop_id, real_path)
