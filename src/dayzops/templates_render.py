"""Renderização do template canônico do server.yaml.

Single source of truth: src/dayzops/templates/server.yaml.template.

Razão de existir: o heredoc inline no install.sh e o examples/server.yaml
divergiam silenciosamente. Agora o template fica no pacote (importlib.resources),
o install.sh chama `dayzops render-config`, e o examples/ pode ser regenerado.

Placeholders suportados: {{DAYZ_HOME}}, {{SCHEDULE}}.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("templates")

TEMPLATE_NAME = "server.yaml.template"


def _read_template() -> str:
    """Lê o template do pacote via importlib.resources.

    Funciona quando o pacote está instalado (pip install / .whl) E em modo
    editável (pip install -e .) — desde que o template esteja em
    src/dayzops/templates/ e seja incluído em package-data (pyproject.toml).
    """
    pkg = resources.files("dayzops") / "templates" / TEMPLATE_NAME
    return pkg.read_text(encoding="utf-8")


def render_server_yaml(
    *,
    dayz_home: str = "/srv/dayz",
    schedule: str = "04:00",
    template_text: str | None = None,
) -> str:
    """Renderiza o template substituindo placeholders.

    Parâmetro `template_text` é opcional (testes injetam direto sem ler pacote).
    """
    text = template_text if template_text is not None else _read_template()
    rendered = (
        text
        .replace("{{DAYZ_HOME}}", str(dayz_home))
        .replace("{{SCHEDULE}}", str(schedule))
    )
    return rendered


def write_server_yaml(
    output: Path,
    *,
    dayz_home: str = "/srv/dayz",
    schedule: str = "04:00",
    overwrite: bool = False,
) -> Path:
    """Renderiza e escreve em `output`. Não sobrescreve por default.

    Retorna o path escrito. Se output já existe e overwrite=False, devolve
    o path sem fazer nada (log info).
    """
    output = Path(output)
    if output.exists() and not overwrite:
        log.info("config já existe em %s (mantido)", output)
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_server_yaml(dayz_home=dayz_home, schedule=schedule),
        encoding="utf-8",
    )
    log.info("config renderizado em %s", output)
    return output
