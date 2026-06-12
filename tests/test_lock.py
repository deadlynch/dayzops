import pytest

from dayzops.lock import global_lock, LockError


def test_acquires_and_releases(tmp_path):
    lock_file = tmp_path / "dayzops.lock"

    with global_lock(lock_file):
        pass  # adquiriu sem erro

    # Depois de liberado, dá pra adquirir de novo.
    with global_lock(lock_file):
        pass


def test_second_acquisition_aborts(tmp_path):
    lock_file = tmp_path / "dayzops.lock"

    # flock distingue file descriptions independentes, então um segundo
    # global_lock() no mesmo processo conflita com o primeiro — exatamente
    # o que aconteceria entre dois processos dayzops concorrentes.
    with global_lock(lock_file):
        with pytest.raises(LockError):
            with global_lock(lock_file):
                pass


def test_lock_released_after_exception(tmp_path):
    lock_file = tmp_path / "dayzops.lock"

    # Mesmo que o bloco estoure, o lock precisa ser liberado (finally).
    with pytest.raises(ValueError):
        with global_lock(lock_file):
            raise ValueError("boom")

    with global_lock(lock_file):
        pass  # conseguiu readquirir → lock foi liberado
