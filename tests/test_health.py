import pytest

from dayzops.health import HealthChecker, HealthError


class _Control:
    """is_active() vira True depois de `become_active_after` chamadas."""
    def __init__(self, become_active_after=0):
        self.calls = 0
        self.threshold = become_active_after

    def is_active(self):
        self.calls += 1
        return self.calls > self.threshold


def test_passes_when_active_immediately():
    hc = HealthChecker(_Control(0), sleep=lambda s: None)
    hc.wait()  # não levanta


def test_retries_until_active():
    control = _Control(become_active_after=2)  # ativa na 3a checagem
    slept = []
    hc = HealthChecker(control, interval=3, sleep=lambda s: slept.append(s))
    hc.wait()
    assert control.calls == 3
    assert slept == [3, 3]  # dormiu duas vezes antes de passar


def test_times_out_when_never_active():
    control = _Control(become_active_after=999)
    with pytest.raises(HealthError):
        HealthChecker(control, timeout=6, interval=3, sleep=lambda s: None).wait()


def test_port_check_required_when_port_set():
    control = _Control(0)  # processo sempre ativo
    # porta fechada -> nunca saudável -> timeout
    hc = HealthChecker(control, port=2302, timeout=3, interval=3,
                       sleep=lambda s: None, port_check=lambda h, p, **k: False)
    with pytest.raises(HealthError):
        hc.wait()


def test_port_check_passes_when_open():
    control = _Control(0)
    hc = HealthChecker(control, port=2302, sleep=lambda s: None,
                       port_check=lambda h, p, **k: True)
    hc.wait()  # processo ativo + porta aberta
