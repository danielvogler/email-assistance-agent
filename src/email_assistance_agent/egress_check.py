"""Prove the network blocks sending: run inside the deployment's VPC.

Deployed as a Cloud Run job with the same network and egress settings as the
service. It exits non-zero unless every SMTP port is blocked and IMAP is
reachable, so a firewall change that reopens sending fails loudly.
"""

from __future__ import annotations

import socket
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

PROBE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Probe:
    """One host and port, and whether the deployment must allow it."""

    host: str
    port: int
    must_be_open: bool


PROBES: tuple[Probe, ...] = (
    Probe("smtp.gmail.com", 465, must_be_open=False),
    Probe("smtp.gmail.com", 587, must_be_open=False),
    Probe("smtp-relay.gmail.com", 587, must_be_open=False),
    Probe("smtp-relay.gmail.com", 465, must_be_open=False),
    Probe("imap.gmail.com", 993, must_be_open=True),
)

Connector = Callable[[tuple[str, int], float], socket.socket]


def is_open(probe: Probe, connect: Connector) -> bool:
    """Try a TCP connection; any failure counts as blocked."""
    try:
        connect((probe.host, probe.port), PROBE_TIMEOUT_SECONDS).close()
    except OSError:
        return False
    return True


def run(probes: Sequence[Probe], connect: Connector) -> list[str]:
    """Probe every target and return the violations, printing one line each."""
    violations: list[str] = []
    for probe in probes:
        state = "OPEN" if is_open(probe, connect) else "BLOCKED"
        print(f"{probe.host}:{probe.port} {state}")
        if (state == "OPEN") != probe.must_be_open:
            expected = "open" if probe.must_be_open else "blocked"
            violations.append(f"{probe.host}:{probe.port} should be {expected}")
    return violations


def main() -> None:
    """Exit 0 when sending is blocked and IMAP works, 1 otherwise."""
    violations = run(PROBES, socket.create_connection)
    if violations:
        print("FAIL: " + "; ".join(violations))
        sys.exit(1)
    print("PASS: SMTP is blocked and IMAP is reachable")
