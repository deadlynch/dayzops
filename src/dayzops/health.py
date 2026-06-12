import socket
import time

from dayzops.logger import get_logger

log = get_logger("health")


class HealthError(Exception):
    """Levantada quando o servidor não fica saudável dentro do timeout."""


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class HealthChecker:
    """Confirma que o servidor subiu de verdade (passo final do ADR-0006).

    Faz polling com retries até um timeout: o servidor demora a inicializar,
    então checar uma única vez logo após o start daria falso-negativo.

    Por padrão verifica só o nível de processo (systemctl is-active), que é
    o sinal confiável. O check de porta é opcional e injetável — uma query
    A2S/UDP de verdade fica como refinamento futuro (DayZ usa UDP, e detectar
    'porta UDP aberta' por socket é pouco confiável).
    """

    def __init__(
        self,
        control,
        *,
        port: int | None = None,
        host: str = "127.0.0.1",
        timeout: int = 60,
        interval: int = 3,
        sleep=time.sleep,
        port_check=_port_open,
    ):
        self.control = control
        self.port = port
        self.host = host
        self.timeout = timeout
        self.interval = interval
        self._sleep = sleep
        self._port_check = port_check

    def _healthy_once(self) -> bool:
        if not self.control.is_active():
            return False
        if self.port is not None:
            return self._port_check(self.host, self.port)
        return True

    def wait(self) -> None:
        """Faz polling até saudável; levanta HealthError se estourar o timeout."""
        elapsed = 0
        while True:
            if self._healthy_once():
                log.info("health check ok (após %ds)", elapsed)
                return
            if elapsed >= self.timeout:
                raise HealthError(f"servidor não ficou saudável em {self.timeout}s")
            self._sleep(self.interval)
            elapsed += self.interval
