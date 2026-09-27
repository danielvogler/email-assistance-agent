"""The no-send pre-commit hook still matches what it is meant to stop."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def hook_pattern(hook_id: str) -> re.Pattern[str]:
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == hook_id:
                return re.compile(hook["entry"])
    raise AssertionError(f"hook {hook_id} is missing from .pre-commit-config.yaml")


@pytest.mark.parametrize(
    "line",
    [
        "import smtplib",
        "from smtplib import SMTP_SSL",
        "server = SMTP('smtp.gmail.com', 587)",
        "server.sendmail(a, b, msg)",
        "server.send_message(msg)",
        "service.users().drafts().send(userId='me', body=d)",
        "service.users().messages.send(userId='me')",
        "requests.post(base + '/send')",
    ],
)
def test_hook_catches_send_code(line: str) -> None:
    assert hook_pattern("no-send-code").search(line)


@pytest.mark.parametrize("line", ["append_draft(client, folder, draft, now)", "def list_drafts(limit): ..."])
def test_hook_allows_draft_code(line: str) -> None:
    assert not hook_pattern("no-send-code").search(line)


def test_source_tree_is_clean() -> None:
    pattern = hook_pattern("no-send-code")
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{number}"
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        for number, text in enumerate(path.read_text().splitlines(), start=1)
        if pattern.search(text)
    ]

    assert offenders == []


def test_service_account_key_hook_matches_a_key_file() -> None:
    assert hook_pattern("no-gcp-service-account-keys").search('{\n  "type": "service_account",')


def test_hook_catches_socket_send() -> None:
    assert hook_pattern("no-send-code").search("sock.send(b'MAIL FROM:<a@b>')")


def test_commit_message_hook_rejects_ai_attribution() -> None:
    pattern = re.compile(hook_pattern("no-agent-coauthors").pattern, re.IGNORECASE)

    assert pattern.search("Co-Authored-By: Claude <noreply@anthropic.com>")
    assert pattern.search("Generated with Claude Code")
    assert not pattern.search("fix(mail): quote the search query")
