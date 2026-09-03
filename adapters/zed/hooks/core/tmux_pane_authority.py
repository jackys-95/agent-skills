#!/usr/bin/env python3
"""Core cross-harness tmux pane-turn authority.

CC and Codex lifecycle hooks share one claim per tmux server and pane. The
claim authorizes only one harness session and prompt generation to inject into
that pane. State is file-backed, stdlib-only, and deployed flat beside callers.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


CLAIM_VERSION = 1
STATE_DIR = Path("/tmp")
SUPPORTED_HARNESSES = frozenset({"cc", "codex"})


@dataclass(frozen=True)
class OwnerIdentity:
    pid: int
    start: str


@dataclass(frozen=True)
class PaneIdentity:
    harness: str
    session_id: str
    owner_pid: int
    owner_start: str

    @classmethod
    def from_owner(cls, harness, session_id, owner):
        return cls(harness, session_id, owner.pid, owner.start)


@dataclass(frozen=True)
class PaneClaim:
    tmux_server: str
    tmux_pane: str
    version: int
    harness: str
    session_id: str
    turn_authority_token: str
    owner_pid: int
    owner_start: str

    @property
    def identity(self):
        return PaneIdentity(
            self.harness,
            self.session_id,
            self.owner_pid,
            self.owner_start,
        )


def canonical_tmux_server(tmux_server):
    """Return the socket-and-PID identity shared across one tmux server."""
    if not isinstance(tmux_server, str) or not tmux_server.strip():
        raise ValueError("tmux server identity must be a non-empty string")
    value = tmux_server.strip()
    parts = value.rsplit(",", 2)
    if len(parts) == 3 and parts[1].isdigit():
        socket_path = os.path.realpath(parts[0])
        return f"{socket_path},{parts[1]}"
    return value


def canonical_tmux_pane(tmux_pane):
    if not isinstance(tmux_pane, str) or not tmux_pane.strip():
        raise ValueError("tmux pane must be a non-empty string")
    return tmux_pane.strip()


def _pane_key(tmux_server, tmux_pane):
    material = json.dumps(
        [canonical_tmux_server(tmux_server), canonical_tmux_pane(tmux_pane)],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def pane_claim_path(tmux_server, tmux_pane):
    return STATE_DIR / f"zed_tmux_pane_{_pane_key(tmux_server, tmux_pane)}.json"


def pane_claim_lock_path(tmux_server, tmux_pane):
    return STATE_DIR / f"zed_tmux_pane_{_pane_key(tmux_server, tmux_pane)}.lock"


def process_start_time(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    start = " ".join(result.stdout.split())
    return start or None


def current_owner_identity():
    pid = os.getppid()
    start = process_start_time(pid)
    if start is None:
        return None
    return OwnerIdentity(pid, start)


def is_live_owner(owner):
    if not isinstance(owner, OwnerIdentity):
        return False
    return process_start_time(owner.pid) == owner.start


def _valid_identity(identity):
    return (
        isinstance(identity, PaneIdentity)
        and identity.harness in SUPPORTED_HARNESSES
        and isinstance(identity.session_id, str)
        and bool(identity.session_id)
        and isinstance(identity.owner_pid, int)
        and not isinstance(identity.owner_pid, bool)
        and identity.owner_pid > 0
        and isinstance(identity.owner_start, str)
        and bool(identity.owner_start)
    )


def _valid_claim(claim):
    return (
        isinstance(claim, PaneClaim)
        and isinstance(claim.version, int)
        and not isinstance(claim.version, bool)
        and claim.version == CLAIM_VERSION
        and _valid_identity(claim.identity)
        and isinstance(claim.turn_authority_token, str)
        and bool(claim.turn_authority_token)
        and isinstance(claim.tmux_server, str)
        and bool(claim.tmux_server)
        and isinstance(claim.tmux_pane, str)
        and bool(claim.tmux_pane)
    )


def _claim_payload(claim):
    return {
        "version": claim.version,
        "harness": claim.harness,
        "session_id": claim.session_id,
        "turn_authority_token": claim.turn_authority_token,
        "owner_pid": claim.owner_pid,
        "owner_start": claim.owner_start,
    }


def _claim_from_payload(tmux_server, tmux_pane, payload):
    if not isinstance(payload, dict):
        return None
    try:
        claim = PaneClaim(
            tmux_server=canonical_tmux_server(tmux_server),
            tmux_pane=canonical_tmux_pane(tmux_pane),
            version=payload["version"],
            harness=payload["harness"],
            session_id=payload["session_id"],
            turn_authority_token=payload["turn_authority_token"],
            owner_pid=payload["owner_pid"],
            owner_start=payload["owner_start"],
        )
    except (KeyError, AttributeError, TypeError, ValueError):
        return None
    return claim if _valid_claim(claim) else None


@contextmanager
def _pane_lock(tmux_server, tmux_pane, *, exclusive):
    path = pane_claim_lock_path(tmux_server, tmux_pane)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(descriptor, mode)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _read_claim_unlocked(tmux_server, tmux_pane):
    path = pane_claim_path(tmux_server, tmux_pane)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return _claim_from_payload(tmux_server, tmux_pane, payload)


def _write_claim_unlocked(claim):
    path = pane_claim_path(claim.tmux_server, claim.tmux_pane)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as claim_file:
            descriptor = None
            json.dump(
                _claim_payload(claim),
                claim_file,
                sort_keys=True,
                separators=(",", ":"),
            )
            claim_file.write("\n")
            claim_file.flush()
            os.fsync(claim_file.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except OSError:
            pass


def read_pane_claim(tmux_server, tmux_pane):
    try:
        with _pane_lock(tmux_server, tmux_pane, exclusive=False):
            return _read_claim_unlocked(tmux_server, tmux_pane)
    except (OSError, ValueError):
        return None


def claim_pane_turn(
    tmux_server,
    tmux_pane,
    harness,
    session_id,
    owner_identity,
    token=None,
):
    if not isinstance(owner_identity, OwnerIdentity):
        raise ValueError("invalid owner identity")
    identity = PaneIdentity.from_owner(harness, session_id, owner_identity)
    claim = PaneClaim(
        tmux_server=canonical_tmux_server(tmux_server),
        tmux_pane=canonical_tmux_pane(tmux_pane),
        version=CLAIM_VERSION,
        harness=identity.harness,
        session_id=identity.session_id,
        turn_authority_token=token or secrets.token_urlsafe(24),
        owner_pid=identity.owner_pid,
        owner_start=identity.owner_start,
    )
    if not _valid_claim(claim):
        raise ValueError("invalid pane claim")
    with _pane_lock(tmux_server, tmux_pane, exclusive=True):
        _write_claim_unlocked(claim)
    return claim


def claim_matches_identity(claim, identity):
    return (
        _valid_claim(claim)
        and _valid_identity(identity)
        and claim.identity == identity
    )


def is_current_pane_claim(expected_claim):
    if not _valid_claim(expected_claim):
        return False
    try:
        with _pane_lock(
            expected_claim.tmux_server,
            expected_claim.tmux_pane,
            exclusive=False,
        ):
            current = _read_claim_unlocked(
                expected_claim.tmux_server,
                expected_claim.tmux_pane,
            )
            return (
                current is not None
                and current == expected_claim
                and is_live_owner(
                    OwnerIdentity(current.owner_pid, current.owner_start)
                )
            )
    except (OSError, ValueError):
        return False


def _remove_claim_unlocked(tmux_server, tmux_pane):
    try:
        pane_claim_path(tmux_server, tmux_pane).unlink()
    except FileNotFoundError:
        return False
    return True


def revoke_mismatched_pane_claim(tmux_server, tmux_pane, identity):
    if not _valid_identity(identity):
        return False
    try:
        with _pane_lock(tmux_server, tmux_pane, exclusive=True):
            current = _read_claim_unlocked(tmux_server, tmux_pane)
            if current is None or current.identity == identity:
                return False
            return _remove_claim_unlocked(tmux_server, tmux_pane)
    except (OSError, ValueError):
        return False


def revoke_owned_pane_claim(tmux_server, tmux_pane, identity):
    if not _valid_identity(identity):
        return False
    try:
        with _pane_lock(tmux_server, tmux_pane, exclusive=True):
            current = _read_claim_unlocked(tmux_server, tmux_pane)
            if current is None or current.identity != identity:
                return False
            return _remove_claim_unlocked(tmux_server, tmux_pane)
    except (OSError, ValueError):
        return False


def serialize_expected_claim(claim):
    if not _valid_claim(claim):
        raise ValueError("invalid expected pane claim")
    payload = _claim_payload(claim)
    payload["tmux_server"] = claim.tmux_server
    payload["tmux_pane"] = claim.tmux_pane
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def deserialize_expected_claim(value):
    try:
        payload = json.loads(value)
        tmux_server = payload.pop("tmux_server")
        tmux_pane = payload.pop("tmux_pane")
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return _claim_from_payload(tmux_server, tmux_pane, payload)
