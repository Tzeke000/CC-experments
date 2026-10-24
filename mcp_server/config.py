"""Bridge configuration (issue #3).

The bridge URL and request timeout are configuration, never hard-coded in
library code (see .opencode/rules/architecture.md). Defaults are localhost-only.

Making Things morph (decision C): bridge auth token is required by default —
auto-minted to a local file when unset. Opt out only with
``GODOT_MCP_ALLOW_INSECURE_BRIDGE=1`` (tests / explicit insecure local use).
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger("godot_mcp.config")

DEFAULT_BRIDGE_URL = "ws://localhost:9080"
DEFAULT_REQUEST_TIMEOUT = 10.0
# #563: websockets' default inbound max_size is 1 MiB — a full 3D gameplay
# screenshot (base64 PNG) exceeds it and the listener would drop the frame.
# 32 MiB mirrors the addon's WebSocketPeer buffer raise in mcp_bridge.gd.
DEFAULT_MAX_INBOUND_MESSAGE_BYTES = 32 * 1024 * 1024

# MCP HTTP transport defaults (distinct from Godot's bridge port 9080).
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 9090

# Environment overrides.
BRIDGE_URL_ENV = "GODOT_MCP_BRIDGE_URL"
# Shared secret for the bridge handshake (issue #538). Making Things requires
# a token by default (decision C); unset → mint to BRIDGE_TOKEN_FILE.
BRIDGE_TOKEN_ENV = "GODOT_MCP_BRIDGE_TOKEN"
# Explicit opt-out of bridge auth (tests / insecure local only).
ALLOW_INSECURE_BRIDGE_ENV = "GODOT_MCP_ALLOW_INSECURE_BRIDGE"
# Override path for the auto-minted / shared bridge token file.
BRIDGE_TOKEN_FILE_ENV = "GODOT_MCP_BRIDGE_TOKEN_FILE"
# HTTP Host/Origin protection (issue #636). Unset = "auto" (protect loopback);
# set "false" to opt out, or "true"/"strict" to validate every request.
HOST_ORIGIN_PROTECTION_ENV = "GODOT_MCP_HTTP_HOST_ORIGIN_PROTECTION"

DEFAULT_BRIDGE_TOKEN_FILE = (
    Path.home() / ".config" / "making-things-godot" / "bridge.token"
)

Transport = Literal["stdio", "http"]
HostOriginProtection = bool | Literal["auto"]


def _parse_transport(value: str | None) -> Transport:
    """Validate and narrow a transport string to the supported literal."""
    if value == "stdio":
        return "stdio"
    if value == "http":
        return "http"
    return "stdio"


def _parse_host_origin_protection(value: str | None) -> HostOriginProtection:
    """Parse the HTTP Host/Origin protection setting (issue #636).

    Unset / empty / ``auto`` → ``"auto"`` (the safe default: validate a
    loopback-bound server). ``false``/``0``/``no``/``off`` → ``False`` (opt out).
    ``true``/``1``/``yes``/``on``/``strict`` → ``True`` (validate every request).
    An unrecognized value falls back to the safe default rather than failing.
    """
    if value is None:
        return "auto"
    normalized = value.strip().lower()
    if normalized in ("", "auto"):
        return "auto"
    if normalized in ("false", "0", "no", "off"):
        return False
    if normalized in ("true", "1", "yes", "on", "strict"):
        return True
    return "auto"


def bridge_token_file_path() -> Path:
    """Path used to persist / share the bridge token with the Godot addon dock."""
    override = os.environ.get(BRIDGE_TOKEN_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_BRIDGE_TOKEN_FILE


def _allow_insecure_bridge() -> bool:
    return os.environ.get(ALLOW_INSECURE_BRIDGE_ENV, "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_bridge_auth_token() -> str | None:
    """Resolve the bridge shared secret (env → file → mint), or None if insecure.

    Making Things decision C: token from day one. Production path always returns
    a non-empty token unless ``GODOT_MCP_ALLOW_INSECURE_BRIDGE`` is set.
    """
    env_token = (os.environ.get(BRIDGE_TOKEN_ENV) or "").strip()
    if env_token:
        return env_token

    path = bridge_token_file_path()
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token

    if _allow_insecure_bridge():
        return None

    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    logger.warning(
        "minted GODOT_MCP_BRIDGE_TOKEN at %s (mode 0600); set the same token in "
        "the Godot addon dock / GODOT_MCP_BRIDGE_TOKEN, or export the env var",
        path,
    )
    return token


class BridgeConfig(BaseModel):
    """Connection settings for the Godot addon bridge."""

    url: str = DEFAULT_BRIDGE_URL
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    # Shared secret (issue #538 + Making Things decision C): when set, the addon
    # must send a matching token as its first message after connecting or the
    # peer is refused at the handshake. None only when insecure bridge allowed.
    auth_token: str | None = None
    # #563: inbound message cap for the listener (websockets ``max_size``).
    # The 1 MiB library default drops large screenshot frames the addon sends.
    max_inbound_message_bytes: int = DEFAULT_MAX_INBOUND_MESSAGE_BYTES

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Build config from the environment, falling back to localhost defaults."""
        return cls(
            url=os.environ.get(BRIDGE_URL_ENV, DEFAULT_BRIDGE_URL),
            auth_token=resolve_bridge_auth_token(),
        )


class ServerConfig(BaseModel):
    """Top-level MCP server configuration.

    Transport defaults to ``stdio`` (the spec'd, auth-free local transport);
    ``http`` exposes the server over Streamable HTTP for clients that want a
    long-lived shared server.

    There is no per-mode "permission" gate: safety is enforced by per-tool
    ``safety_class`` + ``dry_run``/``confirm`` (issue #14), plus the optional
    human-in-the-loop :class:`~mcp_server.safety.ApprovalGate` webhook below.
    """

    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    transport: Transport = "stdio"
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT
    log_level: str = "INFO"
    # Runtime loop (issue #13): path to the Godot binary and the project directory.
    # Both optional — the binary is auto-discovered and the project dir falls back to
    # the connected editor's project.
    godot_bin: str | None = None
    godot_project_dir: str | None = None
    # Human-in-the-loop approval (issue #14/#153). Opt-in: with no webhook,
    # destructive tools run as before (so evals/headless are never blocked).
    # ``fail_open`` decides whether an unreachable webhook approves or denies;
    # it defaults to **False** (fail closed) per issue #638 — set
    # GODOT_MCP_APPROVAL_FAIL_OPEN=true to opt into fail-open.
    approval_webhook: str | None = None
    approval_timeout: float = 30.0
    approval_fail_open: bool = False
    # Guard-pattern approval (issue #346). Opt-in: with no webhook, a
    # mutating/destructive tool returns an InputRequiredResult (an elicitation
    # the client fulfils and re-calls) instead of raising. Durable + stateless;
    # see .opencode/rules/async-patterns.md. Ignored when a webhook is set
    # (the webhook path keeps its existing raise-on-deny behavior).
    approval_require: bool = False
    # Consent-token HMAC key (#759). Unset → a random per-process key (tokens do
    # not survive a restart; fine for a short-lived local token).
    consent_secret: str | None = None
    # HTTP transport auth (issue #226). Opt-in: loopback HTTP is allowed without a
    # token; a non-loopback bind requires a token or the server refuses to start.
    auth_token: str | None = None
    # HTTP DNS-rebinding protection (issue #636). FastMCP's HostOriginGuardMiddleware
    # ships off; default "auto" validates the Host header (and a browser Origin) for
    # a loopback-bound server — a foreign Host yields 421, a foreign Origin 403,
    # before any code-executing tool is reachable. ``False`` opts out; ``True``
    # validates every request ("strict"). See HOST_ORIGIN_PROTECTION_ENV.
    http_host_origin_protection: HostOriginProtection = "auto"
    # Opt-in update check (issue #629). Off by default — no silent phone-home; when
    # set, the server may query the release feed to tell the agent it is behind.
    check_updates: bool = False

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Build full server config from the environment."""
        return cls(
            bridge=BridgeConfig.from_env(),
            transport=_parse_transport(os.environ.get("GODOT_MCP_TRANSPORT", "stdio")),
            host=os.environ.get("GODOT_MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
            port=int(os.environ.get("GODOT_MCP_HTTP_PORT", DEFAULT_HTTP_PORT)),
            log_level=os.environ.get("GODOT_MCP_LOG_LEVEL", "INFO"),
            godot_bin=os.environ.get("GODOT_MCP_GODOT_BIN"),
            godot_project_dir=os.environ.get("GODOT_MCP_PROJECT_DIR"),
            approval_webhook=os.environ.get("GODOT_MCP_APPROVAL_WEBHOOK"),
            approval_timeout=float(os.environ.get("GODOT_MCP_APPROVAL_TIMEOUT", 30.0)),
            approval_fail_open=os.environ.get("GODOT_MCP_APPROVAL_FAIL_OPEN", "false").lower()
            in ("1", "true", "yes"),
            approval_require=os.environ.get("GODOT_MCP_APPROVAL_REQUIRE", "").lower()
            in ("1", "true", "yes"),
            consent_secret=os.environ.get("GODOT_MCP_CONSENT_SECRET") or None,
            auth_token=os.environ.get("GODOT_MCP_AUTH_TOKEN"),
            http_host_origin_protection=_parse_host_origin_protection(
                os.environ.get(HOST_ORIGIN_PROTECTION_ENV)
            ),
            check_updates=os.environ.get("GODOT_MCP_CHECK_UPDATES", "").lower()
            in ("1", "true", "yes"),
        )

    def validate_http_auth(self) -> None:
        """Refuse a non-loopback HTTP bind unless an auth token is configured.

        Loopback (127.0.0.1 / localhost) is the default and safe without auth.
        Binding off-loopback exposes unauthenticated code execution (write_script,
        run_and_capture, export) — require a token or fail fast with a clear error.
        stdio is never gated (local subprocess).
        """
        if self.transport != "http":
            return
        if self.auth_token:
            return
        host = self.host
        if host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
            raise ValueError(
                f"HTTP transport bound to {host} (non-loopback) without GODOT_MCP_AUTH_TOKEN. "
                "Binding off-loopback exposes unauthenticated code execution. "
                "Set GODOT_MCP_AUTH_TOKEN to a bearer token, or bind 127.0.0.1."
            )
