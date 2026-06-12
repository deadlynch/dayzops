"""Módulo de interação com o SteamCMD para download/atualização do servidor DayZ."""

import os
import subprocess
import sys
import logging
from typing import Optional, Callable, List

# Configuração básica de logging (caso não exista)
log = logging.getLogger("dayzops.steamcmd")

# ------------------------------------------------------------------------------
# Exceções específicas do módulo
# ------------------------------------------------------------------------------

class SteamCmdError(Exception):
    """Erro genérico na execução do steamcmd."""
    pass


class SteamCmd2FARequiredError(SteamCmdError):
    """Lançada quando o Steam Guard (2FA) é exigido e não foi fornecido."""
    pass


# ------------------------------------------------------------------------------
# Classe principal
# ------------------------------------------------------------------------------

class SteamCmd:
    """Interface para executar comandos do SteamCMD."""

    def __init__(
        self,
        username: str,
        password: Optional[str] = None,
        runner: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None,
    ):
        """
        Inicializa a instância do SteamCMD.

        Args:
            username: Nome de usuário Steam.
            password: Senha da Steam (opcional, pode ser fornecida via env).
            runner: Função que executa o comando (para testes).
        """
        self.username = username
        # Prioriza a senha passada diretamente, senão tenta da variável de ambiente
        self.password = password or os.environ.get("DAYZOPS_STEAM_PASSWORD", "")
        self._runner = runner or self._default_runner

    def _redact(self, command: List[str]) -> List[str]:
        """Remove a senha da linha de comando para logs seguros."""
        redacted = []
        skip_next = False
        for token in command:
            if skip_next:
                redacted.append("********")
                skip_next = False
                continue
            if token == "+password":
                skip_next = True
            redacted.append(token)
        return redacted

    def build_command(self, steam_actions: List[str]) -> List[str]:
        """Constrói a lista de argumentos para o steamcmd."""
        cmd = ["steamcmd"]
        if self.username:
            cmd.extend(["+login", self.username])
            if self.password:
                cmd.extend(["+password", self.password])
        cmd.extend(steam_actions)
        cmd.append("+quit")
        return cmd

    # --------------------------------------------------------------------------
    # Runner interativo com suporte a 2FA
    # --------------------------------------------------------------------------

    def _default_runner(self, command: List[str]) -> subprocess.CompletedProcess:
        """
        Executa o steamcmd de forma interativa, suportando Steam Guard (2FA).

        Lê a saída linha a linha, detecta a solicitação do código 2FA e
        injeta o código automaticamente (via variável de ambiente ou input).
        """
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # redireciona stderr para stdout para capturar mensagens 2FA
            text=True,
            bufsize=1,                   # line-buffered
        )

        stdout_lines = []
        two_factor_detected = False

        while True:
            if process.stdout is None:
                break
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if not line:
                continue

            stdout_lines.append(line)

            # Detecta a solicitação do código 2FA (Steam Guard)
            if not two_factor_detected and (
                "Steam Guard" in line or "Two-factor" in line or "Please check your email" in line
            ):
                two_factor_detected = True
                two_factor_code = os.environ.get("DAYZOPS_STEAM_2FA_CODE")

                if not two_factor_code:
                    # Se não houver variável de ambiente, tenta ler interativamente
                    if not sys.stdin.isatty():
                        raise SteamCmd2FARequiredError(
                            "Código 2FA necessário, mas não há terminal interativo. "
                            "Defina a variável de ambiente DAYZOPS_STEAM_2FA_CODE."
                        )
                    two_factor_code = input(f"[dayzops] Código 2FA para conta {self.username}: ").strip()

                # Envia o código para o processo steamcmd
                if process.stdin:
                    process.stdin.write(two_factor_code + "\n")
                    process.stdin.flush()
                    log.debug("Código 2FA enviado para o steamcmd.")

        process.wait()
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=''.join(stdout_lines),
            stderr=''
        )

    # --------------------------------------------------------------------------
    # Execução principal
    # --------------------------------------------------------------------------

    def run(self, steam_actions: List[str]) -> subprocess.CompletedProcess:
        """
        Executa uma lista de ações no steamcmd.

        Args:
            steam_actions: Lista de argumentos do steamcmd (ex: ["+app_update", "223350"])

        Returns:
            subprocess.CompletedProcess com o resultado da execução.

        Raises:
            SteamCmdError: Se o steamcmd retornar código de saída diferente de zero.
            SteamCmd2FARequiredError: Se o 2FA for necessário e não puder ser fornecido.
        """
        command = self.build_command(steam_actions)
        log.info("steamcmd: %s", " ".join(self._redact(command)))

        result = self._runner(command)

        if result.returncode != 0:
            tail = (result.stdout or "")[-500:]
            raise SteamCmdError(
                f"steamcmd falhou (exit {result.returncode}).\n"
                f"Saída final:\n{tail}"
            )
        return result

    # --------------------------------------------------------------------------
    # Ações comuns do SteamCMD
    # --------------------------------------------------------------------------

    def install_or_update_server(self, install_dir: str) -> subprocess.CompletedProcess:
        """Instala ou atualiza o servidor DayZ no diretório especificado."""
        actions = [
            f"+force_install_dir {install_dir}",
            "+app_update 223350 validate",
        ]
        return self.run(actions)

    def validate(self, install_dir: str) -> subprocess.CompletedProcess:
        """Valida os arquivos do servidor DayZ."""
        actions = [
            f"+force_install_dir {install_dir}",
            "+app_update 223350 validate",
        ]
        return self.run(actions)
