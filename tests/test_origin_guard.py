"""Unit tests for the same-origin guard + request-body size cap
(nodes/image/factory/_origin_guard.py — 待回答 #47 security fix).

Imports the module directly by file path (same technique as
tests/test_path_traversal.py) so this test does NOT import the plugin's real
root __init__.py — that pulls in the live ComfyUI host and is exactly the
load-bearing pytest quirk documented in .claude/CLAUDE.md's "Test-runner
quirk" section. _origin_guard.py itself has zero ComfyUI dependencies (aiohttp
is imported lazily, only inside guard_same_origin()), so it is safe to import
this way even though aiohttp IS a real dependency used by some tests below.

Run from the plugin root exactly as quality-gates/run.py g3 does:
    (cwd=tests) pytest --rootdir=.. --confcutdir=.. test_origin_guard.py
"""
import asyncio
import importlib.util
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_GUARD_FILE = os.path.join(_HERE, "..", "nodes", "image", "factory", "_origin_guard.py")
_spec = importlib.util.spec_from_file_location("_misaka_origin_guard", _GUARD_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

check_same_origin = _mod.check_same_origin
guard_same_origin = _mod.guard_same_origin
read_capped_body = _mod.read_capped_body
content_length_exceeds_cap = _mod.content_length_exceeds_cap
BodyTooLarge = _mod.BodyTooLarge
MAX_PROFILE_BODY_BYTES = _mod.MAX_PROFILE_BODY_BYTES
ALLOWED_HOSTS_ENV_VAR = _mod.ALLOWED_HOSTS_ENV_VAR

SERVER_PORT = 8188  # ComfyUI's real default port — used as the "actual bound port" in every case


@pytest.fixture(autouse=True)
def _clear_allowed_hosts_env(monkeypatch):
    # Every test starts with MISAKA_PM_ALLOWED_HOSTS unset, regardless of
    # whatever the real host environment happens to have -- a test that
    # needs it set does so itself via monkeypatch.setenv, which reverts
    # automatically at test teardown.
    monkeypatch.delenv(ALLOWED_HOSTS_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# check_same_origin() — pure-function matrix. No aiohttp, no I/O.
# ---------------------------------------------------------------------------

def test_matching_origin_passes():
    ok, _ = check_same_origin(
        "POST", {"Origin": "http://127.0.0.1:8188", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is True


def test_foreign_origin_rejected():
    ok, reason = check_same_origin(
        "POST", {"Origin": "http://evil.example.com", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_null_origin_rejected():
    ok, reason = check_same_origin(
        "POST", {"Origin": "null", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is False and "null" in reason.lower()


def test_origin_same_host_different_port_rejected():
    # Origin claims port 9999 while the real Host header says 8188 — the
    # Origin/Host comparison itself fails before the server-port check even runs.
    ok, reason = check_same_origin(
        "POST", {"Origin": "http://127.0.0.1:9999", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_origin_present_host_missing_rejected():
    ok, reason = check_same_origin(
        "POST", {"Origin": "http://127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is False and "Host" in reason


def test_no_origin_cross_site_rejected():
    ok, reason = check_same_origin(
        "POST", {"Sec-Fetch-Site": "cross-site", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_no_origin_no_sec_fetch_site_passes():
    ok, _ = check_same_origin(
        "POST", {"Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is True


def test_host_port_mismatch_rejected():
    # Origin and Host AGREE with each other (both say :9999) but that is not
    # the port ComfyUI is actually bound to (8188) — the DNS-rebinding guard
    # catches this even though the Origin/Host pair is internally consistent.
    ok, reason = check_same_origin(
        "POST", {"Origin": "http://127.0.0.1:9999", "Host": "127.0.0.1:9999"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_host_no_port_vs_server_8188_rejected():
    # No Origin, no Sec-Fetch-Site — passes stage 1, but the bare Host (no
    # port -> defaults to scheme default 80 for http) does not match 8188.
    ok, reason = check_same_origin(
        "POST", {"Host": "127.0.0.1"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_host_trailing_dot_with_origin_rejected():
    # Documented choice: a trailing dot is NOT stripped, so "127.0.0.1." is a
    # literally different host string from the Origin's "127.0.0.1" -> reject.
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://127.0.0.1:8188", "Host": "127.0.0.1.:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is False and reason


def test_host_trailing_dot_without_origin_passes_port_check():
    # Without an Origin to compare against, only the Host-port check applies,
    # and the trailing dot does not affect port extraction -> passes.
    ok, _ = check_same_origin(
        "POST", {"Host": "127.0.0.1.:8188"}, "http", SERVER_PORT
    )
    assert ok is True


def test_host_0000_variant_no_special_case():
    # 0.0.0.0 is compared like any other literal host string — no special-case
    # rejection. Origin and Host agree with each other AND with server_port.
    ok, _ = check_same_origin(
        "POST", {"Origin": "http://0.0.0.0:8188", "Host": "0.0.0.0:8188"}, "http", SERVER_PORT
    )
    assert ok is True


def test_server_port_none_skips_port_check():
    # server_port unavailable -> the DNS-rebinding sub-check is skipped
    # entirely (caller is responsible for logging the WARNING).
    ok, _ = check_same_origin(
        "POST", {"Origin": "http://127.0.0.1:9999", "Host": "127.0.0.1:9999"}, "http", None
    )
    assert ok is True


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_read_only_methods_unguarded(method):
    # A read-only route is never guarded — even an obviously-foreign Origin passes.
    ok, _ = check_same_origin(
        method, {"Origin": "http://evil.example.com", "Host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is True


def test_case_insensitive_header_lookup():
    ok, _ = check_same_origin(
        "POST", {"origin": "http://127.0.0.1:8188", "host": "127.0.0.1:8188"}, "http", SERVER_PORT
    )
    assert ok is True


# ---------------------------------------------------------------------------
# F1 fix pass (opus review of 27859b4): a DNS name in the Host header must be
# rejected even when Origin/Host agree with each other AND with server_port —
# that combination is exactly what an attacker who rebinds their own DNS name
# to 127.0.0.1 can produce. Only an IP literal / localhost / an explicitly
# opted-in MISAKA_PM_ALLOWED_HOSTS entry may pass this check.
# ---------------------------------------------------------------------------

def test_dns_rebinding_host_matching_origin_rejected():
    # Attacker's own page, served on port 8188 (ComfyUI's own default), whose
    # DNS name has been rebound to resolve to 127.0.0.1. Origin and Host
    # agree with each other and the port matches server_port -- the OLD
    # port-only check would have passed this.
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://attacker.example:8188", "Host": "attacker.example:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is False and reason


def test_dns_rebinding_host_no_origin_rejected():
    # Same rebinding case but the client sends no Origin at all (falls
    # through the Sec-Fetch-Site stage) -- must still be rejected on the
    # Host-hostname check alone.
    ok, reason = check_same_origin(
        "POST", {"Host": "attacker.example:8188"}, "http", SERVER_PORT
    )
    assert ok is False and reason


def test_allowed_hosts_env_opts_in_configured_hostname(monkeypatch):
    monkeypatch.setenv(ALLOWED_HOSTS_ENV_VAR, "mypc.local")
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://mypc.local:8188", "Host": "mypc.local:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is True, reason


def test_allowed_hosts_env_does_not_opt_in_other_hostnames(monkeypatch):
    # Opting in "mypc.local" must not accidentally permit an unrelated DNS
    # name.
    monkeypatch.setenv(ALLOWED_HOSTS_ENV_VAR, "mypc.local")
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://attacker.example:8188", "Host": "attacker.example:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is False and reason


@pytest.mark.parametrize("entry", ["*", "http://x", "a:1", "user@host"])
def test_malformed_allowed_hosts_entries_are_dropped(monkeypatch, entry):
    # A malformed entry must not grant permission to any hostname a naive
    # parse might extract from it (e.g. "x" out of "http://x", "a" out of
    # "a:1", "host" out of "user@host") -- nor to the literal entry itself.
    monkeypatch.setenv(ALLOWED_HOSTS_ENV_VAR, entry)
    for candidate_host in {entry, "x", "a", "host", "*"}:
        ok, reason = check_same_origin(
            "POST", {"Host": f"{candidate_host}:8188"}, "http", SERVER_PORT
        )
        assert ok is False, f"host {candidate_host!r} should not be permitted via malformed entry {entry!r}"


def test_malformed_allowed_hosts_entry_logs_warning_once(monkeypatch, caplog):
    # Reset the once-per-entry dedup set first -- an earlier test in this
    # file may already have triggered the "*" warning, which would otherwise
    # make this assertion order-dependent.
    _mod._warned_malformed_allowed_hosts.clear()
    monkeypatch.setenv(ALLOWED_HOSTS_ENV_VAR, "*")
    with caplog.at_level("WARNING"):
        check_same_origin("POST", {"Host": "attacker.example:8188"}, "http", SERVER_PORT)
    assert any("malformed" in r.message.lower() for r in caplog.records)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1:8188",
        "[::1]:8188",
        "localhost:8188",
        "0.0.0.0:8188",
        "192.168.1.50:8188",
        "127.0.0.1.:8188",  # trailing dot -- still an IP literal after stripping it
    ],
)
def test_ip_literal_and_localhost_hosts_still_permitted(host):
    # Every legitimate deployment shape from before this fix pass must keep
    # working with no Origin header (so only the Host-hostname/port checks
    # apply).
    ok, reason = check_same_origin("POST", {"Host": host}, "http", SERVER_PORT)
    assert ok is True, reason


# ---------------------------------------------------------------------------
# F2 fix pass: a malformed Origin port must never raise out of the guard --
# it must be treated as "cannot parse" -> reject, same as any other
# unparseable Origin.
# ---------------------------------------------------------------------------

def test_parse_origin_malformed_port_suffix_returns_none_tuple():
    assert _mod._parse_origin("http://127.0.0.1:8188.evil.example") == (None, None, None)


def test_parse_origin_port_out_of_range_returns_none_tuple():
    assert _mod._parse_origin("http://127.0.0.1:99999999") == (None, None, None)


def test_malformed_origin_port_suffix_rejected_not_raised():
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://127.0.0.1:8188.evil.example", "Host": "127.0.0.1:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is False and reason


def test_malformed_origin_port_out_of_range_rejected_not_raised():
    ok, reason = check_same_origin(
        "POST",
        {"Origin": "http://127.0.0.1:99999999", "Host": "127.0.0.1:8188"},
        "http",
        SERVER_PORT,
    )
    assert ok is False and reason


# ---------------------------------------------------------------------------
# F3 fix pass: _warned_origins must not grow without bound.
# ---------------------------------------------------------------------------

def test_warned_origins_set_is_capped():
    _mod._warned_origins.clear()
    for i in range(_mod._MAX_WARNED_ORIGINS + 50):
        _mod._log_rejected_origin(f"http://evil-{i}.example", "test reason")
    assert len(_mod._warned_origins) <= _mod._MAX_WARNED_ORIGINS
    _mod._warned_origins.clear()


# ---------------------------------------------------------------------------
# guard_same_origin() — real aiohttp Request objects via make_mocked_request
# (aiohttp is a genuine dependency of this plugin and is present in the gate
# interpreter, so this exercises the actual aiohttp-facing integration point,
# not just the pure function above).
# ---------------------------------------------------------------------------

def _mocked_request(method, headers, scheme="http"):
    from aiohttp.test_utils import make_mocked_request

    # sslcontext controls aiohttp's own request.scheme property; leave None
    # for "http", pass a truthy sentinel for "https".
    sslcontext = object() if scheme == "https" else None
    return make_mocked_request(method, "/misaka/save_profile", headers=headers, sslcontext=sslcontext)


def test_guard_same_origin_matching_passes():
    req = _mocked_request("POST", {"Origin": "http://127.0.0.1:8188", "Host": "127.0.0.1:8188"})
    result = asyncio.run(guard_same_origin(req, SERVER_PORT))
    assert result is None


def test_guard_same_origin_foreign_returns_403_json():
    req = _mocked_request("POST", {"Origin": "http://evil.example.com", "Host": "127.0.0.1:8188"})
    result = asyncio.run(guard_same_origin(req, SERVER_PORT))
    assert result is not None
    assert result.status == 403
    body = json.loads(result.body.decode("utf-8"))
    assert "error" in body


def test_guard_same_origin_none_port_still_functions_and_warns(caplog):
    req = _mocked_request("POST", {"Origin": "http://127.0.0.1:8188", "Host": "127.0.0.1:8188"})
    with caplog.at_level("WARNING"):
        result = asyncio.run(guard_same_origin(req, None))
    # Origin/Host agree with each other, and with no server_port there is
    # nothing to contradict -> passes, but a WARNING must be logged.
    assert result is None
    assert any("could not determine" in r.message.lower() or "port" in r.message.lower() for r in caplog.records)


def test_guard_same_origin_dns_rebinding_host_returns_403(monkeypatch):
    # F1, at the real aiohttp-facing integration point (not just the pure
    # function): a rebound DNS name whose Origin/Host agree with each other
    # AND with server_port must still 403.
    monkeypatch.delenv(ALLOWED_HOSTS_ENV_VAR, raising=False)
    req = _mocked_request("POST", {"Origin": "http://attacker.example:8188", "Host": "attacker.example:8188"})
    result = asyncio.run(guard_same_origin(req, SERVER_PORT))
    assert result is not None
    assert result.status == 403


def test_guard_same_origin_malformed_origin_port_returns_403_not_raises():
    # F2, at the real aiohttp-facing integration point: a malformed Origin
    # port must produce a clean 403 JSON response, never an unhandled
    # ValueError (which would otherwise surface as a 500 in the real route,
    # since guard_same_origin() is called before save_profile's own
    # try/except).
    req = _mocked_request(
        "POST",
        {"Origin": "http://127.0.0.1:8188.evil.example", "Host": "127.0.0.1:8188"},
    )
    result = asyncio.run(guard_same_origin(req, SERVER_PORT))
    assert result is not None
    assert result.status == 403
    body = json.loads(result.body.decode("utf-8"))
    assert "error" in body


# ---------------------------------------------------------------------------
# read_capped_body() — real aiohttp StreamReader, both the fast
# (Content-Length header) and slow (streamed / chunked, no reliable
# Content-Length) paths that save_profile's route handler exercises.
# ---------------------------------------------------------------------------

def test_read_capped_body_under_cap_returns_full_bytes():
    payload = b"x" * 1024

    async def run():
        req = None
        loop = asyncio.get_running_loop()
        from aiohttp.base_protocol import BaseProtocol
        from aiohttp.streams import StreamReader
        from aiohttp.test_utils import make_mocked_request

        protocol = BaseProtocol(loop=loop)
        stream = StreamReader(protocol, limit=2**16, loop=loop)
        stream.feed_data(payload)
        stream.feed_eof()
        req = make_mocked_request("POST", "/misaka/save_profile", payload=stream)
        return await read_capped_body(req, MAX_PROFILE_BODY_BYTES)

    result = asyncio.run(run())
    assert result == payload


def test_read_capped_body_streamed_over_cap_raises():
    # Simulates a client that does NOT send a (trustworthy) Content-Length —
    # the cap must still be enforced by the streaming read itself.
    oversized = b"x" * (MAX_PROFILE_BODY_BYTES + 1)

    async def run():
        loop = asyncio.get_running_loop()
        from aiohttp.base_protocol import BaseProtocol
        from aiohttp.streams import StreamReader
        from aiohttp.test_utils import make_mocked_request

        protocol = BaseProtocol(loop=loop)
        stream = StreamReader(protocol, limit=2**20, loop=loop)
        stream.feed_data(oversized)
        stream.feed_eof()
        req = make_mocked_request("POST", "/misaka/save_profile", payload=stream)
        await read_capped_body(req, MAX_PROFILE_BODY_BYTES)

    with pytest.raises(BodyTooLarge):
        asyncio.run(run())


# ---------------------------------------------------------------------------
# content_length_exceeds_cap() — the fast-path decision save_profile's
# handler itself makes, BEFORE ever reading the body stream. Rewritten
# (F4, opus review of 27859b4): the previous version of this test asserted
# only that aiohttp's own make_mocked_request correctly parsed a
# Content-Length header and that one number is greater than another -- it
# would have kept passing even if __init__.py's content_length fast path
# were deleted outright. This version calls the actual function the
# handler calls.
# ---------------------------------------------------------------------------

def test_content_length_over_cap_detected_without_reading_body():
    # request has no attached payload stream at all -- if this function ever
    # tried to read the body, it would raise/hang rather than answer from
    # the header alone.
    from aiohttp.test_utils import make_mocked_request

    req = make_mocked_request(
        "POST",
        "/misaka/save_profile",
        headers={"Content-Length": str(MAX_PROFILE_BODY_BYTES + 1)},
    )
    assert content_length_exceeds_cap(req.content_length) is True


def test_content_length_exceeds_cap_true_over():
    assert content_length_exceeds_cap(MAX_PROFILE_BODY_BYTES + 1) is True


def test_content_length_exceeds_cap_false_at_cap():
    # Exactly at the cap must pass (`>` not `>=`), matching read_capped_body.
    assert content_length_exceeds_cap(MAX_PROFILE_BODY_BYTES) is False


def test_content_length_exceeds_cap_false_when_none():
    # Content-Length absent (e.g. chunked transfer-encoding) is never "over
    # cap" at this fast-path stage -- read_capped_body's streamed read is
    # what catches that case.
    assert content_length_exceeds_cap(None) is False
