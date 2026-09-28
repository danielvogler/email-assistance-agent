"""Reject browser requests and unknown Host headers before MCP sees them.

This replaces the MCP SDK's DNS-rebinding check because that one only knows
exact host names. Cloud Run gives a service two names, and `gcloud run
services proxy` uses the legacy one, which contains a hash that is only known
after the service exists. So the allowlist accepts wildcard patterns such as
`email-agent-alex-*.a.run.app`.

The check that matters most is Origin: a browser always sends it, MCP clients
do not, and it is what stops a web page from reaching the local proxy.
"""

from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatchcase
from typing import Any

from starlette.responses import PlainTextResponse

ASGIApp = Any


def host_allowed(host: str, patterns: Iterable[str]) -> bool:
    """True if the Host header matches one allowlist pattern (`*` is a wildcard)."""
    candidate = host.strip().lower()
    return bool(candidate) and any(fnmatchcase(candidate, pattern.strip().lower()) for pattern in patterns)


class RequestGuard:
    """ASGI middleware: no browser origins, and only allowlisted Host headers."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = tuple(allowed_hosts)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Check HTTP requests; pass lifespan and other scopes straight through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1") for name, value in scope["headers"]
        }
        if "origin" in headers:
            await PlainTextResponse("Browser requests are not accepted", status_code=403)(
                scope, receive, send
            )
            return
        if not host_allowed(headers.get("host", ""), self.allowed_hosts):
            await PlainTextResponse("Invalid Host header", status_code=421)(scope, receive, send)
            return
        await self.app(scope, receive, send)
