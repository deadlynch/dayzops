import logging

from dayzops.constants import APP_NAME
from dayzops.logger import get_logger


def test_returns_configured_root_logger():
    log = get_logger()
    assert log.name == APP_NAME
    assert log.handlers  # foi configurado com um handler


def test_no_duplicate_handlers():
    get_logger()
    get_logger()
    get_logger("config")

    # Mesmo chamando várias vezes, a raiz mantém exatamente 1 handler.
    root = logging.getLogger(APP_NAME)
    assert len(root.handlers) == 1


def test_child_logger_uses_namespaced_name():
    log = get_logger("config")
    assert log.name == f"{APP_NAME}.config"


def test_child_has_no_own_handler():
    # O filho não tem handler próprio; ele propaga até a raiz.
    child = get_logger("config")
    assert child.handlers == []
    assert child.propagate is True
