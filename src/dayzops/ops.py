from dataclasses import dataclass, field
from typing import Callable

from dayzops.constants import LOCK_FILE
from dayzops.lock import global_lock
from dayzops.logger import get_logger
from dayzops.state import StateStore

log = get_logger("ops")


class UpdateError(Exception):
    """Levantada quando o update falha e o backup é restaurado."""


def _stub(step_name: str) -> Callable:
    """Cria um passo placeholder que apenas avisa que ainda não existe.

    Padrão Null Object: o workflow roda de ponta a ponta hoje, mesmo com
    passos não implementados, em vez de quebrar. Cada etapa futura substitui
    um stub por uma implementação real.
    """
    def _fn(*args, **kwargs):
        log.warning("passo '%s' ainda não implementado — pulando (stub)", step_name)
    return _fn


@dataclass
class UpdatePlan:
    """Colaboradores do workflow de update (ADR-0006).

    `update_server` é obrigatório (já existe via SteamCmd). Os demais têm
    default = stub e serão preenchidos nas próximas etapas. Injetar todos os
    passos deixa o workflow inteiro testável sem tocar em servidor real.
    """
    update_server: Callable
    create_backup: Callable = field(default_factory=lambda: _stub("create_backup"))
    restore_backup: Callable = field(default_factory=lambda: _stub("restore_backup"))
    stop_server: Callable = field(default_factory=lambda: _stub("stop_server"))
    update_mods: Callable = field(default_factory=lambda: _stub("update_mods"))
    validate: Callable = field(default_factory=lambda: _stub("validate"))
    sync_keys: Callable = field(default_factory=lambda: _stub("sync_keys"))
    start_server: Callable = field(default_factory=lambda: _stub("start_server"))
    health_check: Callable = field(default_factory=lambda: _stub("health_check"))


def run_update(
    plan: UpdatePlan,
    *,
    store: StateStore | None = None,
    lock_file=LOCK_FILE,
) -> dict:
    """Executa o workflow atômico de update do ADR-0006.

    Tudo roda sob o lock global, então duas operações críticas nunca se
    atropelam. Se a validação falhar, o backup é restaurado e a versão
    anterior volta a subir — o servidor nunca fica num estado inutilizável.
    """
    store = store or StateStore()

    with global_lock(lock_file):
        log.info("update: iniciando")

        plan.create_backup()
        plan.stop_server()

        plan.update_server()
        plan.update_mods()

        # Ponto de não-retorno: se a validação falhar, desfazemos tudo.
        try:
            plan.validate()
        except Exception as exc:
            log.error("validação falhou: %s — restaurando backup", exc)
            plan.restore_backup()
            plan.start_server()  # sobe a versão anterior
            raise UpdateError("update abortado; backup restaurado") from exc

        plan.sync_keys()
        plan.start_server()
        plan.health_check()

        store.record_update(status="success")
        inventory = store.write_inventory()
        log.info("update: concluído")
        return inventory
