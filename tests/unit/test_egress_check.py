from __future__ import annotations

import socket
from typing import Any

import pytest

from email_assistance_agent import egress_check
from email_assistance_agent.egress_check import PROBES, Probe, run


class FakeSocket:
    def close(self) -> None:
        pass


def connector(open_ports: set[int]) -> Any:
    def connect(address: tuple[str, int], timeout: float) -> FakeSocket:
        if address[1] not in open_ports:
            raise TimeoutError("timed out")
        return FakeSocket()

    return connect


def test_passes_when_smtp_blocked_and_imap_open(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(PROBES, connector({993})) == []
    assert "imap.gmail.com:993 OPEN" in capsys.readouterr().out


def test_open_smtp_is_a_violation() -> None:
    violations = run([Probe("smtp.gmail.com", 587, must_be_open=False)], connector({587}))

    assert violations == ["smtp.gmail.com:587 should be blocked"]


def test_blocked_imap_is_a_violation() -> None:
    assert run([Probe("imap.gmail.com", 993, must_be_open=True)], connector(set())) == [
        "imap.gmail.com:993 should be open"
    ]


def test_every_smtp_submission_port_is_probed() -> None:
    blocked = {(p.host, p.port) for p in PROBES if not p.must_be_open}

    assert {("smtp.gmail.com", 465), ("smtp.gmail.com", 587)} <= blocked


@pytest.mark.parametrize(("open_ports", "code"), [({993}, None), ({465, 993}, 1)])
def test_main_exit_code(monkeypatch: pytest.MonkeyPatch, open_ports: set[int], code: int | None) -> None:
    monkeypatch.setattr(socket, "create_connection", connector(open_ports))

    if code is None:
        egress_check.main()
    else:
        with pytest.raises(SystemExit) as excinfo:
            egress_check.main()
        assert excinfo.value.code == code
