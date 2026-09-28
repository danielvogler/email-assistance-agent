from __future__ import annotations

import pytest

from email_assistance_agent.http_guard import host_allowed

PATTERNS = ("localhost:*", "127.0.0.1:*", "svc-123.europe-west6.run.app", "svc-*.a.run.app")


@pytest.mark.parametrize(
    "host",
    [
        "localhost:8080",
        "127.0.0.1:18080",
        "svc-123.europe-west6.run.app",
        "svc-6dlg5woxea-oa.a.run.app",
        "SVC-X.A.RUN.APP",
    ],
)
def test_allowed_hosts(host: str) -> None:
    assert host_allowed(host, PATTERNS)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "evil.example",
        "svc-6dlg5woxea-oa.a.run.app.evil.example",
        "other-6dlg5woxea-oa.a.run.app",
        "localhost",
    ],
)
def test_rejected_hosts(host: str) -> None:
    assert not host_allowed(host, PATTERNS)
