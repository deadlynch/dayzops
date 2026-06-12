import subprocess

from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("systemd")

SERVER_SERVICE = "dayz"         # dayz.service  (systemctl start dayz)
UPDATE_SERVICE = "dayz-update"  # dayz-update.service + dayz-update.timer


class SystemdError(Exception):
    pass


# ---------------------------------------------------------------------------
# Geração de units (puro: entra config, sai texto — fácil de testar)
# ---------------------------------------------------------------------------

def render_server_unit(*, exec_start: str, working_dir: str, user: str = "dayz") -> str:
    """Conteúdo do dayz.service — o servidor DayZ em si.

    Logs vão pro journald automaticamente (stdout/stderr), casando com a
    escolha de logging da etapa 2.
    """
    return (
        "[Unit]\n"
        "Description=DayZ Dedicated Server\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={user}\n"
        f"WorkingDirectory={working_dir}\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def render_update_service(*, dayzops_bin: str = "dayzops", user: str = "dayz") -> str:
    """Conteúdo do dayz-update.service — oneshot que roda 'dayzops update'."""
    return (
        "[Unit]\n"
        "Description=DayZ scheduled update (dayzops)\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"User={user}\n"
        f"ExecStart={dayzops_bin} update\n"
    )


def render_update_timer(*, schedule: str = "04:00") -> str:
    """Conteúdo do dayz-update.timer. `schedule` vira OnCalendar (ex: 04:00)."""
    return (
        "[Unit]\n"
        "Description=DayZ scheduled update timer (dayzops)\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {schedule}:00\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def generate_units(
    out_dir: Path,
    *,
    exec_start: str,
    working_dir: str,
    schedule: str = "04:00",
    user: str = "dayz",
    dayzops_bin: str = "dayzops",
) -> dict:
    """Gera as três units a partir do config (ADR-0001: single source of truth)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    units = {
        f"{SERVER_SERVICE}.service": render_server_unit(
            exec_start=exec_start, working_dir=working_dir, user=user
        ),
        f"{UPDATE_SERVICE}.service": render_update_service(
            dayzops_bin=dayzops_bin, user=user
        ),
        f"{UPDATE_SERVICE}.timer": render_update_timer(schedule=schedule),
    }

    written = {}
    for name, content in units.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written[name] = path
        log.info("unit gerada: %s", name)
    return written


# ---------------------------------------------------------------------------
# Controle do serviço (efeito colateral: subprocesso isolado e injetável)
# ---------------------------------------------------------------------------

class ServerControl:
    """Liga/desliga/reinicia o serviço do servidor via systemctl (ADR-0002).

    Os métodos start()/stop() são o que o workflow de update (ops.py) injeta
    como stop_server/start_server.
    """

    def __init__(self, service: str = SERVER_SERVICE, *, use_sudo: bool = True, runner=None):
        self.service = service
        self.use_sudo = use_sudo
        self._runner = runner or self._default_runner

    def _default_runner(self, command: list[str]):
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def _systemctl(self, *args: str):
        cmd = (["sudo"] if self.use_sudo else []) + ["systemctl", *args]
        log.info("systemctl: %s", " ".join(cmd))
        return self._runner(cmd)

    def _require_ok(self, result, action: str):
        if result.returncode != 0:
            raise SystemdError(
                f"systemctl {action} {self.service} falhou (exit {result.returncode})"
            )
        return result

    def start(self):
        return self._require_ok(self._systemctl("start", self.service), "start")

    def stop(self):
        return self._require_ok(self._systemctl("stop", self.service), "stop")

    def restart(self):
        return self._require_ok(self._systemctl("restart", self.service), "restart")

    def is_active(self) -> bool:
        result = self._systemctl("is-active", self.service)
        return (getattr(result, "stdout", "") or "").strip() == "active"
