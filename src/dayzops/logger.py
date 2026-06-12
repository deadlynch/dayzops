import logging
import os
import sys

from dayzops.constants import APP_NAME

_DEFAULT_LEVEL = "INFO"


def get_logger(name: str | None = None) -> logging.Logger:
    """Devolve um logger configurado para escrever em stderr.

    Em produção o DayZops roda sob systemd (ADR-0002), então logar em stderr
    deixa o journald capturar tudo — `journalctl -u dayz` com rotação e
    retenção de graça, sem a ferramenta gerenciar arquivos de log.

    Padrão hierárquico: o logger raiz (APP_NAME) é configurado uma única vez
    com um handler; loggers nomeados são "filhos" que propagam até a raiz e
    reaproveitam esse handler. Assim não há handler duplicado (e, portanto,
    nenhuma linha de log repetida).

    Nível controlado pela env var DAYZOPS_LOG_LEVEL (default: INFO).
    """
    root = logging.getLogger(APP_NAME)

    # Configura só na primeira vez. Sem essa guarda, cada chamada adicionaria
    # um novo StreamHandler e as mensagens sairiam repetidas.
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
        root.setLevel(_resolve_level())
        # Não propaga pro root logger global do Python (evita linha dupla
        # caso algo configure o root em outro ponto).
        root.propagate = False

    if name:
        # Filho propaga até APP_NAME e usa o mesmo handler.
        return root.getChild(name)

    return root


def _resolve_level() -> int:
    """Lê DAYZOPS_LOG_LEVEL; cai em INFO se ausente ou inválida."""
    name = os.environ.get("DAYZOPS_LOG_LEVEL", _DEFAULT_LEVEL).upper()

    # getLevelName(nome) devolve o int correspondente; com nome inválido
    # devolve uma string tipo "Level FOO", então validamos o tipo.
    level = logging.getLevelName(name)
    if isinstance(level, int):
        return level

    return logging.INFO