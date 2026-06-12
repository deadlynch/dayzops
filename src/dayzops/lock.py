import errno
import fcntl
import os

from contextlib import contextmanager
from pathlib import Path

from dayzops.constants import LOCK_FILE
from dayzops.logger import get_logger

log = get_logger("lock")


class LockError(Exception):
    """Levantada quando o lock global já está em posse de outra operação."""


@contextmanager
def global_lock(lock_file: Path = LOCK_FILE):
    """Garante exclusão mútua entre operações críticas (ADR-0009).

    Uso:

        from dayzops.lock import global_lock, LockError

        try:
            with global_lock():
                run_update()
        except LockError:
            print("Outra operação já está em andamento")
            return 1

    Implementação: fcntl.flock em modo exclusivo e NÃO-bloqueante (LOCK_NB).
    Se outra operação já detém o lock, abortamos na hora — em vez de ficar
    esperando — que é o comportamento que o ADR-0009 pede.

    Por que flock e não "o arquivo existe?":
      - O flock é liberado pelo kernel quando o processo morre (o fd é
        fechado). Um crash NÃO deixa lock preso.
      - Um lock baseado só na existência do arquivo ficaria órfão após um
        crash, e exigiria limpeza manual.

    Nuance vs. ADR-0009: o arquivo de lock fica permanentemente em /run
    (tmpfs, some no reboot). A exclusão NÃO vem da existência do arquivo, e
    sim do estado do flock. "Lock existe → aborta" do ADR vira, na prática,
    "flock ocupado → aborta". É só um detalhe de implementação; vale anotar
    no ADR pra alinhar o texto com a realidade.
    """
    # /run normalmente já existe; em dev/teste o diretório pode não existir.
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # O fd dessa abertura é o que o flock referencia.
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            # EAGAIN/EWOULDBLOCK (e EACCES em alguns SOs) = lock já ocupado.
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise LockError(
                    f"Outra operação dayzops já está em andamento "
                    f"(lock: {lock_file})"
                ) from exc
            raise  # qualquer outro erro de SO sobe como está

        # Lock adquirido. Grava o PID só para diagnóstico — `cat` no arquivo
        # mostra quem segura o lock. O PID só é confiável enquanto o lock
        # estiver em posse; depois de liberado, é histórico.
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        log.debug("lock adquirido (pid=%s)", os.getpid())

        try:
            yield
        finally:
            log.debug("lock liberado (pid=%s)", os.getpid())
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        # Importante: NÃO removemos o arquivo. flock + unlink tem uma race
        # clássica (outro processo pode abrir o inode antigo e travar um
        # arquivo que já não está no caminho, permitindo dois donos). Deixar
        # o arquivo parado é o padrão correto e mais simples.
        os.close(fd)