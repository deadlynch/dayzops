"""Helpers de ownership de filesystem.

Centraliza chown -> service user pra arquivos e diretórios criados pelo
DayZops, evitando que itens fiquem como root:root depois que o processo
roda via sudo. Aplica-se a TUDO que vai pro filesystem do servidor:
symlinks de mods, keys/, mpmissions, profiles, workshop, etc.

Princípios:
1. Só atua quando o processo é root E service_user != current_user.
   (Em dev/CI rodando sem sudo, vira no-op.)
2. Para symlinks, usa lchown (não segue o link).
3. Para diretórios, recursivo (chown_recursive) é uma operação separada;
   chown_path é single-shot.
4. Best-effort: log de warning em falha mas não levanta — operações de
   sistema (mods.sync, keys.sync) não devem quebrar se chown falhar.
"""
import os
import pwd
import grp
from pathlib import Path

from dayzops.logger import get_logger

log = get_logger("fsperm")


def _resolve_uid_gid(service_user: str | None) -> tuple[int, int] | None:
    """Retorna (uid, gid) do service_user, ou None se não aplicável.

    Não aplicável: rodando como não-root (não temos permissão pra chown
    de qualquer jeito), ou service_user falsy/inexistente.
    """
    if not service_user:
        return None
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return None
    try:
        pw = pwd.getpwnam(service_user)
        return (pw.pw_uid, pw.pw_gid)
    except KeyError:
        log.warning("service_user %r não existe no sistema; chown pulado", service_user)
        return None


def chown_path(path: Path, service_user: str | None) -> None:
    """Chown single-shot — não segue symlink (usa lchown).

    Silencioso em no-op (não-root, service_user falsy, path inexistente).
    Warning em falha, sem raise.
    """
    target = _resolve_uid_gid(service_user)
    if target is None:
        return
    uid, gid = target
    try:
        # lchown não segue link, importante pra symlinks de mods (queremos
        # que o link em si pertença ao service_user, não o alvo).
        os.lchown(path, uid, gid)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("chown falhou em %s: %s", path, e)


def chown_recursive(root: Path, service_user: str | None) -> None:
    """Chown recursivo a partir de um diretório.

    Caminha o tree todo e chown de cada entry (incluindo o próprio root e
    symlinks via lchown). Best-effort.
    """
    target = _resolve_uid_gid(service_user)
    if target is None:
        return
    uid, gid = target
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        return
    try:
        os.lchown(root, uid, gid)
    except OSError as e:
        log.warning("chown falhou em %s: %s", root, e)
        return
    # Walk só faz sentido se for diretório real
    if root.is_dir() and not root.is_symlink():
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames + filenames:
                p = os.path.join(dirpath, name)
                try:
                    os.lchown(p, uid, gid)
                except OSError as e:
                    log.warning("chown falhou em %s: %s", p, e)
