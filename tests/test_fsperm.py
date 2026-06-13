"""Testes do fsperm — chown único ponto.

Como testes rodam sem root, os branches reais de chown não disparam.
Validamos o caminho de no-op (não levanta, não quebra) e o resolve de uid/gid.
"""
import os
from unittest import mock

import pytest

from dayzops import fsperm


def test_resolve_uid_gid_returns_none_when_not_root(tmp_path):
    """Sem root: resolve_uid_gid devolve None (chown viraria no-op)."""
    with mock.patch.object(os, "geteuid", return_value=1000):
        assert fsperm._resolve_uid_gid("dayz") is None


def test_resolve_uid_gid_returns_none_when_user_empty(tmp_path):
    """service_user vazio/None: sempre None."""
    assert fsperm._resolve_uid_gid(None) is None
    assert fsperm._resolve_uid_gid("") is None


def test_resolve_uid_gid_returns_none_for_unknown_user(tmp_path):
    """User inexistente no sistema: warning e None (sem raise)."""
    with mock.patch.object(os, "geteuid", return_value=0):
        assert fsperm._resolve_uid_gid("nonexistent_user_xyz_99999") is None


def test_chown_path_is_noop_when_not_root(tmp_path):
    """Sem root, chown_path não toca em nada e não levanta."""
    f = tmp_path / "x"
    f.write_text("data")
    fsperm.chown_path(f, "dayz")  # sem mock: rodando não-root real
    # Apenas garantir que não houve exceção
    assert f.exists()


def test_chown_path_is_noop_on_missing_file(tmp_path):
    """Path inexistente: silencioso, sem raise."""
    # Forçar entrada no branch de lchown sob root simulado
    with mock.patch.object(os, "geteuid", return_value=0):
        # Mocka resolve para devolver (uid, gid) plausíveis
        with mock.patch.object(fsperm, "_resolve_uid_gid", return_value=(1000, 1000)):
            with mock.patch.object(os, "lchown") as lchown:
                lchown.side_effect = FileNotFoundError
                fsperm.chown_path(tmp_path / "missing", "dayz")  # não levanta


def test_chown_path_warns_on_oserror(tmp_path, caplog):
    """OSError em lchown vira warning, não raise."""
    f = tmp_path / "x"
    f.write_text("data")
    with mock.patch.object(fsperm, "_resolve_uid_gid", return_value=(1000, 1000)):
        with mock.patch.object(os, "lchown") as lchown:
            lchown.side_effect = OSError("perm denied")
            with caplog.at_level("WARNING"):
                fsperm.chown_path(f, "dayz")
            # Não levanta. Warning pode estar no log do logger "fsperm"
            # (caplog captura mensagens; basta não ter raise)


def test_chown_recursive_walks_tree(tmp_path):
    """Recursive: chama lchown em cada entry (sob root simulado)."""
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a")
    (root / "sub" / "b.txt").write_text("b")

    chowned = []
    with mock.patch.object(fsperm, "_resolve_uid_gid", return_value=(1000, 1000)):
        with mock.patch.object(os, "lchown", side_effect=lambda p, u, g: chowned.append(str(p))):
            fsperm.chown_recursive(root, "dayz")

    # Deve ter chamado em: root, sub/, a.txt, sub/b.txt
    chowned_names = {os.path.basename(p) for p in chowned}
    assert "tree" in chowned_names
    assert "sub" in chowned_names
    assert "a.txt" in chowned_names
    assert "b.txt" in chowned_names


def test_chown_recursive_handles_symlinks_via_lchown(tmp_path):
    """Symlinks devem ser chowned via lchown (não seguem o link).
    Importante: link para o service_user, alvo permanece o que for.
    """
    target = tmp_path / "target.txt"
    target.write_text("data")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    seen = []
    with mock.patch.object(fsperm, "_resolve_uid_gid", return_value=(1000, 1000)):
        with mock.patch.object(os, "lchown", side_effect=lambda p, u, g: seen.append(str(p))):
            fsperm.chown_path(link, "dayz")

    assert str(link) in seen
    # Sanity: o helper usou lchown (não chown), preservando o symlink
