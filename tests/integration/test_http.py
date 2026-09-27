"""The HTTP surface: MCP over streamable HTTP and DNS-rebinding protection."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from email_assistance_agent import server

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def app(allowed_hosts: tuple[str, ...] = ("localhost:*", "service.run.app")) -> Any:
    return server.server.streamable_http_app(
        streamable_http_path=server.MCP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=server.transport_security(allowed_hosts),
        host=server.BIND_HOST,
    )


def post(client: TestClient, body: dict[str, Any], **headers: str) -> Any:
    return client.post(server.MCP_PATH, json=body, headers={**HEADERS, **headers})


@pytest.mark.parametrize("host", ["localhost:8080", "service.run.app"])
def test_tools_list_over_http_for_allowed_hosts(host: str) -> None:
    with TestClient(app(), base_url=f"http://{host}") as client:
        assert post(client, INIT).status_code == 200
        response = post(client, LIST)

    assert response.status_code == 200
    assert {t["name"] for t in response.json()["result"]["tools"]} == server.ALLOWED_TOOLS


def test_unknown_host_is_rejected() -> None:
    with TestClient(app(), base_url="http://attacker.example") as client:
        assert post(client, LIST).status_code == 421


def test_any_browser_origin_is_rejected() -> None:
    with TestClient(app(), base_url="http://localhost:8080") as client:
        response = post(client, LIST, origin="http://localhost:8080")

    assert response.status_code == 403


def test_main_fails_fast_with_names_only(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        server.main()

    assert "EMAIL_USER" in str(excinfo.value)
    assert "EMAIL_PASSWORD" in str(excinfo.value)


def test_main_rejects_unsafe_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    monkeypatch.setenv("READ_LABELS", 'a"b')

    with pytest.raises(SystemExit, match="forbidden character"):
        server.main()


def test_main_serves_with_rebinding_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("ALLOWED_HOSTS", "svc.run.app")
    captured: dict[str, Any] = {}
    monkeypatch.setattr(server.server, "run", lambda **kwargs: captured.update(kwargs))

    server.main()

    assert captured["transport"] == "streamable-http"
    assert captured["port"] == 9090
    assert captured["stateless_http"] is True
    security = captured["transport_security"]
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == ["svc.run.app"]
    assert security.allowed_origins == []
