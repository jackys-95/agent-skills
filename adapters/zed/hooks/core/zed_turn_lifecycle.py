#!/usr/bin/env python3
"""Core turn and session lifecycle hook shared by Zed harnesses."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass

import manifest
import tmux_pane_authority as authority


@dataclass(frozen=True)
class HarnessPolicy:
    guard_env: str
    namespace: str
    ignore_child_prompts: bool = False


POLICIES = {
    "cc": HarnessPolicy("CC_ZED_HOOK", "cc_zed"),
    "codex": HarnessPolicy(
        "CODEX_ZED_HOOK",
        "codex_zed",
        ignore_child_prompts=True,
    ),
}


def _load_event():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return event if isinstance(event, dict) else None


def _pane_context(event):
    tmux_server = os.environ.get("TMUX")
    tmux_pane = os.environ.get("TMUX_PANE")
    session_id = event.get("session_id", "")
    if not tmux_server or not tmux_pane or not session_id:
        return None
    owner = authority.current_owner_identity()
    if owner is None:
        return None
    return tmux_server, tmux_pane, session_id, owner


def begin_turn(harness, policy, event):
    if policy.ignore_child_prompts and "agent_id" in event:
        return

    session_id = event.get("session_id", "")
    manifest.clear_turn(policy.namespace, session_id)
    context = _pane_context(event)
    if context is None:
        return
    tmux_server, tmux_pane, session_id, owner = context
    try:
        authority.claim_pane_turn(
            tmux_server,
            tmux_pane,
            harness,
            session_id,
            owner,
        )
    except (OSError, ValueError):
        return


def reconcile_pane_authority(harness, event):
    context = _pane_context(event)
    if context is None:
        return
    tmux_server, tmux_pane, session_id, owner = context
    identity = authority.PaneIdentity.from_owner(harness, session_id, owner)
    event_name = event.get("hook_event_name")
    try:
        if event_name == "SessionStart":
            authority.revoke_mismatched_pane_claim(
                tmux_server,
                tmux_pane,
                identity,
            )
        elif event_name == "SessionEnd":
            authority.revoke_owned_pane_claim(
                tmux_server,
                tmux_pane,
                identity,
            )
    except (OSError, ValueError):
        return


def run(harness, action):
    policy = POLICIES[harness]
    if not os.environ.get(policy.guard_env):
        return
    event = _load_event()
    if event is None:
        return
    if action == "begin":
        begin_turn(harness, policy, event)
    else:
        reconcile_pane_authority(harness, event)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=tuple(POLICIES), required=True)
    parser.add_argument(
        "--action",
        choices=("begin", "reconcile"),
        required=True,
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    run(args.harness, args.action)


if __name__ == "__main__":
    main()
