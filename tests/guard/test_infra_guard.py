"""The OpenTofu never writes key material into state."""

from __future__ import annotations

import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[2] / "infra"
FORBIDDEN_RESOURCES = ("google_service_account_key", "google_secret_manager_secret_version")


def test_no_resource_that_puts_secrets_in_state() -> None:
    declared = {
        match.group(1)
        for path in INFRA.rglob("*.tf")
        for match in re.finditer(r'^\s*(?:resource|data)\s+"([a-z0-9_]+)"', path.read_text(), re.MULTILINE)
    }

    assert declared, "no resources found; is the infra directory where this test expects?"
    assert not declared & set(FORBIDDEN_RESOURCES)


def test_no_public_iam_member_anywhere() -> None:
    offenders = [
        str(path.relative_to(INFRA))
        for path in INFRA.rglob("*.tf")
        if re.search(r'member\s*=\s*"all(Authenticated)?Users"', path.read_text())
    ]

    assert offenders == []
