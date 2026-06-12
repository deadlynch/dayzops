import os
from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("verify")

SERVER_BINARY = "DayZServer"


class VerifyError(Exception):
    """Levantada quando a instalação não está pronta para subir."""


def _service_root(svc) -> Path:
    """Raiz da árvore gerenciada (ancestral comum de install e workshop).

    Conteúdo de mod deve resolver para dentro dela. Se resolver para fora
    (ex.: /root/.steam, de um download feito como root), o servidor — que
    roda como o usuário de serviço — não consegue ler.
    """
    return Path(os.path.commonpath([str(svc.install_dir), str(svc.workshop_dir)]))


def check_install(svc) -> list[str]:
    """Retorna a lista de problemas encontrados (vazia = tudo ok).

    Não levanta — é a versão inspecionável, usada também por diagnósticos.
    """
    problems: list[str] = []
    install_dir = svc.install_dir

    # 1) Binário do servidor presente (um update parcial pode tê-lo apagado).
    if not (install_dir / SERVER_BINARY).exists():
        problems.append(f"binário do servidor ausente: {SERVER_BINARY}")

    # 2) Config do servidor presente.
    server_cfg = svc.config.get("instance", {}).get("config", "serverDZ.cfg")
    if not (install_dir / server_cfg).exists():
        problems.append(f"config do servidor ausente: {server_cfg}")

    # 3) Cada mod ativo tem conteúdo baixado E acessível ao usuário de serviço.
    root = _service_root(svc)
    user = getattr(svc, "service_user", "dayz")
    for mod, mod_dir in zip(svc.all_mods, svc.mod_dirs):
        mod_dir = Path(mod_dir)
        if not mod_dir.exists():  # segue symlink; pendurado também cai aqui
            problems.append(f"conteúdo do mod ausente: {mod.name}")
            continue
        real = mod_dir.resolve()
        try:
            real.relative_to(root)
        except ValueError:
            problems.append(
                f"conteúdo do mod {mod.name} resolve para fora da árvore do "
                f"serviço ({real}) — provavelmente baixado como root e "
                f"inacessível ao usuário '{user}'. Rebaixe como o usuário de "
                f"serviço (o DayZops já faz isso) ou rode: "
                f"sudo chown -R {user}:{user} {root}"
            )

    return problems


def verify_install(svc) -> None:
    """Passo 'validate' do ADR-0006: levanta VerifyError se algo faltar.

    É este erro que faz o run_update() restaurar o backup e subir a versão
    anterior. Sem este portão, um update quebrado subiria assim mesmo.
    """
    problems = check_install(svc)
    if problems:
        log.error("validação falhou: %d problema(s)", len(problems))
        raise VerifyError("; ".join(problems))
    log.info("validação ok")
