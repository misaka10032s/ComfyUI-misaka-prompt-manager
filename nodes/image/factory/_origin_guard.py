"""Same-origin guard + request-body size cap for the `/misaka/*` write routes.

Why same-origin, not a loopback allow-list (deviates from sibling repos' loopback
allow-lists — decision recorded here on purpose so a future reader does not "fix"
it back to the sibling pattern):

ComfyUI has no built-in authentication, so any web page the browser has open can
issue a cross-site POST to a mounted route (CSRF-style write). Several sibling
repos in this cluster gate their own admin-style write routes with a *loopback*
allow-list (only accept requests whose remote address is 127.0.0.1), because
those services are only ever meant to be reached from the same machine.
ComfyUI is different: the standard `--listen` flag is routinely pointed at a
LAN-visible address (`--listen 0.0.0.0`, or a specific LAN IP) so a second
machine on the same network can drive the same ComfyUI instance from its own
browser tab. A loopback check would either reject that legitimate LAN client
outright, or — if written as "allow the configured --listen host" — reduce to
"allow everyone the operator already said is allowed", which is not a real
CSRF defence. Checking that the request's `Origin` (or, as a fallback,
`Sec-Fetch-Site`) actually names *this* ComfyUI instance survives the LAN case:
it distinguishes "a same-origin page/script talking to ComfyUI" from "some other
site the browser happened to have open", regardless of which interface ComfyUI
is bound to.

Both `check_same_origin()` (pure, no I/O, easy to exhaustively unit-test) and
`guard_same_origin()` (the thin aiohttp-facing wrapper actually wired into a
route) are exported so any future `/misaka/*` write route can reuse the same
one-line guard.

This module also carries the request-body size cap used by `save_profile`
(`read_capped_body`) — a small, related "don't let an untrusted client hand you
an unbounded amount of data" concern that lives naturally next to the origin
guard rather than as a third helper module.

DNS-rebinding defence and the reverse-proxy trade-off (fix pass, 2026-09-07,
opus review of the 待回答 #47 commit — see qa_log): the original version of
this module only checked that the `Host` header's *port* matched ComfyUI's
actual bound port, and its docstring claimed that was a DNS-rebinding
defence. It was not: in a rebinding attack the attacker controls both the
DNS name *and* the page that serves it, so they can simply serve their page
on ComfyUI's own default port (8188) and the port check passes trivially.
The actual defence added in this fix pass is that the `Host` header's
*hostname* must be an IP literal (bracket-stripped, trailing dot ignored) or
`localhost` — a DNS name is exactly what an attacker can rebind to
127.0.0.1, but an IP literal cannot be "rebound" the same way. The old port
check is kept as a narrow, secondary hardening layer, not the rebinding
defence itself.

This means a request whose `Host` header names a plain DNS hostname (not an
IP literal / localhost) is now rejected outright — including a
TLS-terminating or hostname-based reverse proxy in front of ComfyUI (e.g.
`comfy.example.com`), or a LAN client reaching ComfyUI via an mDNS name
(e.g. `mypc.local`). That is a known, accepted trade-off: a same-origin
check cannot trust a bare hostname without an explicit operator opt-in, and
`X-Forwarded-*` is deliberately never consulted here (see
`check_same_origin`'s scheme docstring above). An operator who needs one of
those deployments to keep working can opt a specific hostname in via the
`MISAKA_PM_ALLOWED_HOSTS` environment variable — a comma-separated list of
bare hostnames (no scheme, no port, no path, no `*` wildcard). A malformed
entry is dropped and logged once as a WARNING rather than silently ignored
or treated as a crash.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import FrozenSet, Mapping, Optional, Tuple
from urllib.parse import urlsplit

_logger = logging.getLogger(__name__)

# Opt-in escape hatch for the DNS-rebinding Host-hostname check below: a
# comma-separated list of bare hostnames (no scheme/port/path/wildcard) that
# are permitted as a Host header hostname in addition to IP literals and
# `localhost`. Read fresh on every check (not cached at import) so tests and
# an operator's environment changes both take effect without a restart.
ALLOWED_HOSTS_ENV_VAR = "MISAKA_PM_ALLOWED_HOSTS"

# One WARNING per distinct malformed MISAKA_PM_ALLOWED_HOSTS entry (not per
# request) — same dedup rationale as _warned_origins below.
_warned_malformed_allowed_hosts: set = set()

# Methods that change server-side state. GET/HEAD/OPTIONS are read-only and are
# intentionally left unguarded (blocking them would break normal navigation /
# CORS preflights for no security benefit — there is nothing to forge with a GET).
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_DEFAULT_PORTS = {"http": 80, "https": 443}

# One WARNING per distinct rejected Origin value (not per request) — a page
# hammering a rejected origin should not flood the ComfyUI console.
_warned_origins: set = set()

# Cap on _warned_origins' size: a non-browser client can send an unbounded
# number of distinct Origin values, one set entry each, with no natural
# eviction — bound the memory growth in a long-lived ComfyUI process. Past
# this many distinct rejected origins, new ones are still logged, just
# without the per-origin WARNING dedup (acceptable: this only happens under
# sustained abuse from many distinct origins, which is already loud).
_MAX_WARNED_ORIGINS = 256

# Request-body cap for /misaka/save_profile (and any future /misaka/* write
# route that reuses read_capped_body). 1 MiB is generous for a prompt-profile
# JSON document (checkpoint/LoRA names + a handful of text fields) while still
# bounding worst-case disk usage from a single malicious/broken request.
MAX_PROFILE_BODY_BYTES = 1024 * 1024


class BodyTooLarge(Exception):
    """Raised by read_capped_body() when the streamed body exceeds the cap."""

    def __init__(self, limit: int):
        super().__init__(f"request body exceeds {limit} bytes")
        self.limit = limit


def _header_get(headers: Mapping, name: str) -> Optional[str]:
    """Case-insensitive header lookup that works for both a plain dict (tests)
    and aiohttp's CIMultiDictProxy (which is already case-insensitive, so this
    is a no-op fast path there)."""
    if headers is None:
        return None
    value = headers.get(name)
    if value is not None:
        return value
    lname = name.lower()
    for k, v in headers.items():
        if k.lower() == lname:
            return v
    return None


def _default_port(scheme: Optional[str]) -> Optional[int]:
    if scheme is None:
        return None
    return _DEFAULT_PORTS.get(scheme.lower())


def _parse_origin(origin: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """Parse an Origin header value -> (scheme, host, port). host is lowercased
    (Origin/host are case-insensitive per RFC 6454 / RFC 3986). Returns
    (None, None, None) if the value cannot be parsed as `scheme://host[:port]`
    — including a malformed port (`SplitResult.port` raises ValueError lazily
    on attribute access, e.g. a non-numeric or out-of-range port, so that
    access MUST stay inside this try/except too, not just the urlsplit()
    call).
    """
    try:
        parts = urlsplit(origin)
        if not parts.scheme or not parts.hostname:
            return None, None, None
        return parts.scheme, parts.hostname.lower(), parts.port
    except ValueError:
        return None, None, None


def _parse_authority(value: str) -> Tuple[str, Optional[int]]:
    """Parse a Host header value -> (host, port_or_None). Handles a bracketed
    IPv6 literal (`[::1]:8188`); does NOT strip a trailing dot from an
    FQDN-style host (`127.0.0.1.`) — that is treated as a literal, distinct
    host string, which is the conservative choice: it can never make a
    genuinely different host compare as equal, only ever cause an extra
    rejection when a Host header is written unusually."""
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return value, None
        host = value[1:end]
        rest = value[end + 1:]
        if rest.startswith(":"):
            try:
                return host, int(rest[1:])
            except ValueError:
                return host, None
        return host, None
    if ":" in value:
        host, _, port_s = value.rpartition(":")
        try:
            return host, int(port_s)
        except ValueError:
            return value, None
    return value, None


def _is_valid_allowed_host_entry(entry: str) -> bool:
    """A MISAKA_PM_ALLOWED_HOSTS entry must be a bare hostname: no scheme, no
    port, no path, no wildcard, no userinfo. Rejects anything that could
    smuggle in more than "this exact hostname" (e.g. a `*` wildcard, or a
    `scheme://` prefix that would otherwise be silently ignored)."""
    if not entry:
        return False
    if "*" in entry or "/" in entry or ":" in entry or "@" in entry:
        return False
    return True


def _parse_allowed_hosts_env() -> FrozenSet[str]:
    """Parse MISAKA_PM_ALLOWED_HOSTS (comma-separated bare hostnames) fresh
    from the environment on every call — deliberately not cached at import,
    so both an operator's env change and a test's monkeypatch take effect
    immediately. A malformed entry is dropped and logged once (not silently
    ignored, not raised)."""
    raw = os.environ.get(ALLOWED_HOSTS_ENV_VAR, "")
    allowed = set()
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if _is_valid_allowed_host_entry(entry):
            allowed.add(entry.lower())
        elif entry not in _warned_malformed_allowed_hosts:
            _warned_malformed_allowed_hosts.add(entry)
            _logger.warning(
                "[Misaka] Ignoring malformed %s entry %r — must be a bare "
                "hostname (no scheme/port/path/wildcard).",
                ALLOWED_HOSTS_ENV_VAR, entry,
            )
    return frozenset(allowed)


def _host_hostname_permitted(host: str) -> bool:
    """DNS-rebinding defence: True only if `host` (already stripped of any
    IPv6 brackets by _parse_authority) is an IP literal, `localhost`, or
    explicitly opted in via MISAKA_PM_ALLOWED_HOSTS. A DNS name is exactly
    what an attacker can rebind to 127.0.0.1, so a bare DNS name is never
    trusted by default — see the module docstring for the reverse-proxy
    trade-off this implies."""
    h = (host or "").strip().lower().rstrip(".")
    if h == "localhost":
        return True
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        pass
    return h in _parse_allowed_hosts_env()


def check_same_origin(
    method: str,
    headers: Mapping,
    scheme: str,
    server_port: Optional[int],
) -> Tuple[bool, str]:
    """Pure decision function — no I/O, no aiohttp dependency, exhaustively
    unit-testable. Returns (True, "") if the request passes, or
    (False, "<zh-TW reason>") if it should be rejected with 403.

    `scheme` MUST be the request's own actual transport scheme (aiohttp's
    `request.scheme`, which reflects whether the connection itself is
    TLS-terminated) — NEVER a client-supplied header such as
    `X-Forwarded-Proto`, which an attacker controls and which would let them
    forge a matching Origin/scheme pair.

    Rules (state-changing methods only — GET/HEAD/OPTIONS always pass):
    1. `Origin: null` -> reject (opaque origin, e.g. a sandboxed iframe or a
       `file://` page — never legitimate for this API).
    2. `Origin` present -> it must equal `<scheme>://<Host header>` exactly:
       scheme compared literally, host:port compared case-insensitively with
       an absent port normalized to the scheme's default port. Missing Host
       header with an Origin present -> reject (cannot verify).
    3. `Origin` absent -> fall back to `Sec-Fetch-Site`: `cross-site` ->
       reject; anything else (`same-origin`, `same-site`, `none`, or the
       header itself absent — e.g. a non-browser client) -> pass this stage.
    4. Independently of 1-3: if a `Host` header is present, its hostname
       must be an IP literal (bracket-stripped, trailing dot ignored),
       `localhost`, or explicitly listed in the MISAKA_PM_ALLOWED_HOSTS env
       var (comma-separated bare hostnames) — otherwise reject. THIS is the
       actual DNS-rebinding defence: an attacker's DNS name can be rebound
       to resolve to 127.0.0.1, but an IP literal or `localhost` cannot be
       "rebound" the same way, so a bare DNS name is never trusted by
       default. (A reverse-proxy / hostname-based deployment must opt its
       hostname in via the env var, or it will 403 on every write — see the
       module docstring's "reverse-proxy trade-off" paragraph.)
    5. Also independently of 1-3: if a `Host` header is present, its port
       must equal the port ComfyUI is actually bound to (`server_port`).
       This is a narrow, SECONDARY hardening layer, NOT the rebinding
       defence (rule 4 is) — it only stops an attacker who happens to keep
       their own listening port distinct from ComfyUI's. If `server_port`
       is unavailable (None), only this port sub-check is skipped — the
       caller is expected to log a WARNING when that happens.
    """
    if (method or "").upper() not in _STATE_CHANGING_METHODS:
        return True, ""

    origin = _header_get(headers, "Origin")
    host_header = _header_get(headers, "Host")
    sec_fetch_site = _header_get(headers, "Sec-Fetch-Site")

    if origin is not None:
        if origin.strip().lower() == "null":
            return False, "Origin 為 null，拒絕跨來源請求"
        if not host_header:
            return False, "有 Origin 但缺少 Host 標頭，無法驗證同源性"

        o_scheme, o_host, o_port = _parse_origin(origin)
        if o_scheme is None:
            return False, f"無法解析 Origin 標頭：{origin!r}"

        if o_scheme.lower() != (scheme or "").lower():
            return False, f"Origin scheme 與實際連線 scheme 不符：{origin!r} vs {scheme!r}"

        h_host, h_port = _parse_authority(host_header)
        o_port_n = o_port if o_port is not None else _default_port(o_scheme)
        h_port_n = h_port if h_port is not None else _default_port(scheme)
        if (o_host, o_port_n) != (h_host.lower(), h_port_n):
            return False, f"Origin 與 Host 不符：{origin!r} vs {host_header!r}"
    else:
        if sec_fetch_site is not None and sec_fetch_site.strip().lower() == "cross-site":
            return False, "無 Origin 且 Sec-Fetch-Site: cross-site，拒絕跨來源請求"

    if host_header:
        h_host2, h_port2 = _parse_authority(host_header)
        if not _host_hostname_permitted(h_host2):
            return False, (
                f"Host 主機名稱既非 IP 位址或 localhost，也未列於環境變數 "
                f"{ALLOWED_HOSTS_ENV_VAR} 允許清單中，為防止 DNS rebinding 而拒絕："
                f"{host_header!r}"
            )
        if server_port is not None:
            effective_port = h_port2 if h_port2 is not None else _default_port(scheme)
            if effective_port != server_port:
                return False, (
                    f"Host 埠號與伺服器實際埠號不符：{host_header!r} "
                    f"(伺服器埠號={server_port})"
                )

    return True, ""


def _log_rejected_origin(origin_value: Optional[str], reason: str) -> None:
    key = origin_value if origin_value is not None else "<no Origin>"
    if key in _warned_origins:
        return
    if len(_warned_origins) < _MAX_WARNED_ORIGINS:
        _warned_origins.add(key)
    _logger.warning("[Misaka] Rejected cross-origin write request (Origin=%r): %s", origin_value, reason)


async def guard_same_origin(request, server_port: Optional[int]):
    """aiohttp-facing helper for a state-changing route handler. Call it first
    thing in the handler:

        guard = await guard_same_origin(request, _get_server_port())
        if guard is not None:
            return guard

    Returns None when the request passes, or a ready-to-return 403
    `web.json_response` when it must be rejected.
    """
    from aiohttp import web  # local import: keeps this module importable without aiohttp for pure-function tests

    if server_port is None:
        _logger.warning(
            "[Misaka] Could not determine ComfyUI's bound port — same-origin "
            "Host-port (DNS-rebinding) check is being SKIPPED for this request."
        )

    ok, reason = check_same_origin(request.method, request.headers, request.scheme, server_port)
    if ok:
        return None
    _log_rejected_origin(request.headers.get("Origin"), reason)
    return web.json_response({"error": f"跨來源請求遭拒：{reason}"}, status=403)


def content_length_exceeds_cap(
    content_length: Optional[int], max_bytes: int = MAX_PROFILE_BODY_BYTES
) -> bool:
    """The fast-path check `save_profile` runs BEFORE ever touching the body
    stream: True when the request's `Content-Length` header value alone
    already proves the body is over the cap. Pulled out as its own testable
    function (rather than left as an inline comparison in __init__.py) so a
    test can exercise the actual decision the route handler makes, instead
    of merely asserting that aiohttp itself parsed a Content-Length header —
    a `Content-Length` of `None` (e.g. chunked transfer-encoding) is never
    "over cap" here; that case is caught later by `read_capped_body`'s
    streamed read instead.
    """
    return content_length is not None and content_length > max_bytes


async def read_capped_body(request, max_bytes: int = MAX_PROFILE_BODY_BYTES) -> bytes:
    """Read `request`'s body, aborting as soon as more than `max_bytes` have
    been received. Checking `request.content_length` alone is not enough — a
    client can omit Content-Length (chunked transfer-encoding) or simply lie
    about it, so this reads the actual stream incrementally and raises
    BodyTooLarge the moment the real byte count crosses the cap, before ever
    buffering the whole thing.
    """
    chunks = []
    total = 0
    async for chunk in request.content.iter_chunked(65536):
        total += len(chunk)
        if total > max_bytes:
            raise BodyTooLarge(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)
