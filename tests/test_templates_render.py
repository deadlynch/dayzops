"""Testes do templates_render — single source of truth do server.yaml.

Garante:
- render substitui placeholders corretamente
- write_server_yaml é idempotente (não sobrescreve por default)
- overwrite=True força
- examples/server.yaml fica em sync com o template (paridade)
"""
from pathlib import Path

import pytest
import yaml

from dayzops.templates_render import (
    render_server_yaml,
    write_server_yaml,
    _read_template,
)


TEMPLATE_FIXTURE = """\
server:
  name: "X"
paths:
  install_dir: {{DAYZ_HOME}}/server
updates:
  schedule: "{{SCHEDULE}}"
"""


def test_render_substitutes_placeholders():
    out = render_server_yaml(
        dayz_home="/var/dayz",
        schedule="03:30",
        template_text=TEMPLATE_FIXTURE,
    )
    assert "/var/dayz/server" in out
    assert "schedule: \"03:30\"" in out
    assert "{{DAYZ_HOME}}" not in out
    assert "{{SCHEDULE}}" not in out


def test_render_defaults():
    out = render_server_yaml(template_text=TEMPLATE_FIXTURE)
    assert "/srv/dayz/server" in out
    assert "04:00" in out


def test_render_produces_valid_yaml():
    out = render_server_yaml(template_text=TEMPLATE_FIXTURE)
    data = yaml.safe_load(out)
    assert data["server"]["name"] == "X"
    assert data["paths"]["install_dir"] == "/srv/dayz/server"
    assert data["updates"]["schedule"] == "04:00"


def test_write_does_not_overwrite_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "dayzops.templates_render._read_template", lambda: TEMPLATE_FIXTURE
    )
    out = tmp_path / "server.yaml"
    out.write_text("EXISTING_CONTENT", encoding="utf-8")

    result = write_server_yaml(out)

    assert result == out
    assert out.read_text() == "EXISTING_CONTENT"  # preservado


def test_write_overwrites_when_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "dayzops.templates_render._read_template", lambda: TEMPLATE_FIXTURE
    )
    out = tmp_path / "server.yaml"
    out.write_text("OLD", encoding="utf-8")

    write_server_yaml(out, dayz_home="/x", schedule="01:00", overwrite=True)

    content = out.read_text()
    assert "OLD" not in content
    assert "/x/server" in content
    assert "01:00" in content


def test_write_creates_parent_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "dayzops.templates_render._read_template", lambda: TEMPLATE_FIXTURE
    )
    out = tmp_path / "deep" / "subdir" / "server.yaml"

    write_server_yaml(out)

    assert out.exists()


# --- Sanidade do template embarcado (integração com importlib.resources) ---

def test_real_template_is_packaged_and_readable():
    """O template tem que ser lível via importlib.resources."""
    text = _read_template()
    assert "server:" in text
    assert "{{DAYZ_HOME}}" in text
    assert "{{SCHEDULE}}" in text


def test_real_template_renders_to_valid_yaml():
    rendered = render_server_yaml(dayz_home="/srv/dayz", schedule="04:00")
    data = yaml.safe_load(rendered)
    # Estrutura mínima esperada — bate com o que cli/config.py exige
    assert "server" in data
    assert "paths" in data
    assert data["paths"]["install_dir"] == "/srv/dayz/server"
    assert data["updates"]["schedule"] == "04:00"


def test_examples_server_yaml_matches_rendered_template():
    """examples/server.yaml deve ser uma renderização exata do template
    com os defaults. Se este teste quebrar: regenere examples/ com:

        python -c "from dayzops.templates_render import render_server_yaml; \\
                   print(render_server_yaml(), end='')" > examples/server.yaml
    """
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "examples" / "server.yaml"
    if not example.exists():
        pytest.skip("examples/server.yaml ausente (caso de instalação como pacote)")

    expected = render_server_yaml(dayz_home="/srv/dayz", schedule="04:00")
    assert example.read_text(encoding="utf-8") == expected, (
        "examples/server.yaml divergiu do template canônico. "
        "Regenere com a instrução do docstring."
    )
