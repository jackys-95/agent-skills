#!/usr/bin/env python3
"""Check or configure Codex sandbox access for external workflow paths."""

from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import knowledge_base_catalog
from codex_sandbox_config import (
    CodexSandboxConfigError,
    add_sandbox_paths_to_config,
    default_config_path,
    load_sandbox_config_state,
    normalize_path,
    required_sandbox_paths,
)
from knowledge_base_catalog import (
    KnowledgeLearningPair,
    KnowledgeBaseCatalogError,
    NewCollectionPlan,
    ResolvedKnowledgeBaseCollection,
    plan_new_collection,
    resolve_knowledge_learning_pair,
    resolve_knowledge_base_collections,
)

EXIT_MISSING = 1
EXIT_UNSUPPORTED = 2


class CodexSandboxAccessError(ValueError):
    """The requested sandbox access cannot be validated without guessing."""


CommandHandler = Callable[[argparse.Namespace, argparse.ArgumentParser], int]


@dataclass(frozen=True)
class SandboxAccessRequest:
    """Resolved inputs needed to check or update Codex sandbox access."""

    config_path: Path
    collections: tuple[ResolvedKnowledgeBaseCollection, ...]
    approved_paths: dict[str, str]
    required_paths: tuple[str, ...]


def _approved_collection_paths(
    collection_names: list[str],
    approved_path_arguments: list[list[str]],
    command: str = "add-roots",
) -> dict[str, str]:
    requested = list(dict.fromkeys(collection_names))
    approved_paths: dict[str, str] = {}
    for name, path in approved_path_arguments:
        if name in approved_paths:
            raise CodexSandboxAccessError(
                f"Duplicate --expected-root binding for collection {name!r}"
            )
        approved_paths[name] = normalize_path(path)

    missing = [name for name in requested if name not in approved_paths]
    if missing:
        rendered = ", ".join(repr(name) for name in missing)
        raise CodexSandboxAccessError(
            f"{command} requires one --expected-root COLLECTION PATH binding "
            f"for every --collection; missing: {rendered}"
        )

    unexpected = [name for name in approved_paths if name not in requested]
    if unexpected:
        rendered = ", ".join(repr(name) for name in unexpected)
        raise CodexSandboxAccessError(
            "--expected-root supplied for unrequested collection(s): "
            f"{rendered}"
        )
    return approved_paths


def _validate_approved_collection_paths(
    collections: tuple[ResolvedKnowledgeBaseCollection, ...],
    approved_paths: dict[str, str],
) -> None:
    for collection in collections:
        approved_path = approved_paths[collection.name]
        if collection.collection_path != approved_path:
            raise CodexSandboxAccessError(
                f"Collection {collection.name!r} now resolves to "
                f"{collection.collection_path!r}, but approval was for "
                f"{approved_path!r}. Run the sandbox access preflight again and "
                "obtain fresh approval before retrying."
            )


def _persistent_access_command(
    collections: tuple[ResolvedKnowledgeBaseCollection, ...],
) -> str:
    arguments = ["add-roots"]
    for collection in collections:
        arguments.extend(
            [
                "--collection",
                collection.name,
                "--expected-root",
                collection.name,
                collection.collection_path,
            ]
        )
    return shlex.join(arguments)


def _planned_persistent_access_command(
    plan: NewCollectionPlan,
    config_path: Path,
) -> str:
    arguments = [
        "add-roots",
        "--planned-collection",
        plan.planned.name,
        "--contains",
        plan.planned.role,
        "--domain",
        plan.planned.domain,
    ]
    for collection in plan.collections:
        if collection.name != plan.planned.name:
            arguments.extend(["--collection", collection.name])
        arguments.extend(
            [
                "--expected-root",
                collection.name,
                collection.collection_path,
            ]
        )
    arguments.extend(["--config", str(config_path)])
    return shlex.join(arguments)


def _session_access_command(paths: tuple[str, ...]) -> str:
    arguments = ["codex"]
    for path in paths:
        arguments.extend(["--add-dir", path])
    return shlex.join(arguments)


def _print_resolved_collection(
    collection: ResolvedKnowledgeBaseCollection,
    prefix: str = "  ",
) -> None:
    print(
        f"{prefix}{collection.name} "
        f"({collection.role}, {collection.domain}): "
        f"{collection.collection_path}"
    )


def _new_collection_plan_from_args(
    args: argparse.Namespace,
    approved_paths: dict[str, str],
) -> NewCollectionPlan:
    return plan_new_collection(
        args.planned_collection,
        approved_paths[args.planned_collection],
        args.contains,
        args.domain,
    )


def _add_existing_path_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory-root")
    parser.add_argument("--knowledge-root", action="append", default=[])
    parser.add_argument("--collection", action="append", default=[])
    parser.add_argument(
        "--expected-root",
        action="append",
        nargs=2,
        default=[],
        metavar=("COLLECTION", "PATH"),
        help=(
            "Approved collection/path binding. Required once for each "
            "--collection when configuring access; optional for a bound check."
        ),
    )
    parser.add_argument(
        "--config",
        help="Codex config path. Defaults to $CODEX_HOME/config.toml.",
    )


def _add_check_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("check")
    _add_existing_path_arguments(parser)
    parser.set_defaults(
        handler=_handle_check,
        error_prefix="Cannot update sandbox access",
    )


def _add_add_roots_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("add-roots")
    _add_existing_path_arguments(parser)
    parser.add_argument("--planned-collection")
    parser.add_argument(
        "--contains",
        choices=("knowledge", "learning"),
    )
    parser.add_argument("--domain")
    parser.set_defaults(
        handler=_handle_add_roots,
        error_prefix="Cannot update sandbox access",
    )


def _add_plan_new_collection_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "plan-new-collection",
        help=(
            "Check sandbox access for an exact collection path before qmd or "
            "registry registration."
        ),
    )
    parser.add_argument("--collection", required=True)
    parser.add_argument(
        "--expected-root",
        required=True,
        nargs=2,
        metavar=("COLLECTION", "PATH"),
    )
    parser.add_argument(
        "--contains",
        required=True,
        choices=("knowledge", "learning"),
    )
    parser.add_argument("--domain", required=True)
    parser.add_argument(
        "--config",
        help="Codex config path. Defaults to $CODEX_HOME/config.toml.",
    )
    parser.set_defaults(
        handler=_handle_plan_new_collection,
        error_prefix="Cannot plan new collection access",
    )


def _add_resolve_pair_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "resolve-knowledge-learning-pair",
        help="Resolve one same-domain knowledge/learning pair without changing config.",
    )
    parser.add_argument("--collection", required=True)
    parser.set_defaults(
        handler=_handle_resolve_pair,
        error_prefix="Cannot resolve access pair",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_check_parser(subparsers)
    _add_add_roots_parser(subparsers)
    _add_plan_new_collection_parser(subparsers)
    _add_resolve_pair_parser(subparsers)
    return parser


def _config_path(config_argument: str | None) -> Path:
    if config_argument is None:
        return default_config_path()
    return Path(normalize_path(config_argument))


def _require_access_request(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    planned_collection = getattr(args, "planned_collection", None)
    if (
        args.memory_root is None
        and not args.knowledge_root
        and not args.collection
        and planned_collection is None
    ):
        if args.command == "check":
            parser.error(
                "at least one of --memory-root, --knowledge-root, "
                "or --collection is required"
            )
        parser.error(
            "at least one of --memory-root, --knowledge-root, --collection, "
            "or --planned-collection is required"
        )


def _validate_access_arguments(args: argparse.Namespace) -> str | None:
    if args.memory_root is not None:
        normalize_path(args.memory_root)
    for root in args.knowledge_root:
        normalize_path(root)

    planned_collection = getattr(args, "planned_collection", None)
    if planned_collection is not None:
        if args.memory_root is not None or args.knowledge_root:
            raise CodexSandboxAccessError(
                "--planned-collection cannot be combined with direct memory "
                "or knowledge paths"
            )
        if args.contains is None or args.domain is None:
            raise CodexSandboxAccessError(
                "--planned-collection requires --contains and --domain"
            )
    elif args.command == "add-roots" and (
        args.contains is not None or args.domain is not None
    ):
        raise CodexSandboxAccessError(
            "--contains and --domain require --planned-collection"
        )
    return planned_collection


def _resolve_access_collections(
    args: argparse.Namespace,
    planned_collection: str | None,
    approved_paths: dict[str, str],
) -> tuple[ResolvedKnowledgeBaseCollection, ...]:
    if planned_collection is None:
        collections = resolve_knowledge_base_collections(args.collection)
        if collections:
            print("Resolved knowledge collections:")
            for collection in collections:
                _print_resolved_collection(collection)
        return collections

    plan = _new_collection_plan_from_args(args, approved_paths)
    expected_counterparts = [
        collection.name
        for collection in plan.collections
        if collection.name != planned_collection
    ]
    supplied_counterparts = list(dict.fromkeys(args.collection))
    if supplied_counterparts != expected_counterparts:
        rendered = ", ".join(expected_counterparts) or "<none>"
        raise CodexSandboxAccessError(
            "Registered --collection arguments do not match the current "
            f"deterministic counterpart plan; expected: {rendered}"
        )

    print("Validated planned new collection:")
    _print_resolved_collection(plan.planned)
    if plan.same_domain_counterpart is not None:
        print("Validated existing counterpart:")
        _print_resolved_collection(plan.same_domain_counterpart)
    else:
        print(f"No deterministic counterpart: {plan.counterpart_note}.")
    return plan.collections


def _prepare_sandbox_access(args: argparse.Namespace) -> SandboxAccessRequest:
    config_path = _config_path(args.config)
    planned_collection = _validate_access_arguments(args)
    requested_collections = [
        *([planned_collection] if planned_collection is not None else []),
        *args.collection,
    ]
    approved_paths = {}
    if args.command == "add-roots" or args.expected_root:
        approved_paths = _approved_collection_paths(
            requested_collections,
            args.expected_root,
            command=args.command,
        )
    collections = _resolve_access_collections(
        args,
        planned_collection,
        approved_paths,
    )
    knowledge_paths = [
        *args.knowledge_root,
        *(collection.collection_path for collection in collections),
    ]
    required_paths = required_sandbox_paths(
        args.memory_root,
        knowledge_paths,
        include_qmd_state=(
            args.memory_root is not None or planned_collection is not None
        ),
    )
    print("Required sandbox write paths:")
    for path in required_paths:
        print(f"  {path}")
    print(f"Codex config: {config_path}")
    return SandboxAccessRequest(
        config_path=config_path,
        collections=collections,
        approved_paths=approved_paths,
        required_paths=required_paths,
    )


def _handle_check(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    _require_access_request(args, parser)
    request = _prepare_sandbox_access(args)
    if request.approved_paths:
        _validate_approved_collection_paths(
            request.collections,
            request.approved_paths,
        )
    _, _, state = load_sandbox_config_state(
        request.config_path,
        request.required_paths,
    )
    if state.missing_paths:
        print("Missing sandbox write paths:")
        for path in state.missing_paths:
            print(f"  {path}")
        return EXIT_MISSING
    print("Persistent config includes every requested sandbox path.")
    print(
        "Use /status in the active Codex session to verify effective "
        "sandbox paths."
    )
    return 0


def _handle_add_roots(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    _require_access_request(args, parser)
    request = _prepare_sandbox_access(args)
    _validate_approved_collection_paths(
        request.collections,
        request.approved_paths,
    )
    changed, backup = add_sandbox_paths_to_config(
        request.config_path,
        request.required_paths,
    )
    if not changed:
        print("No config change needed.")
    else:
        print("Added persistent Codex sandbox write access.")
        if backup:
            print(f"Backup: {backup}")
        print("Restart Codex, then use /status to verify effective paths.")
    return 0


def _handle_plan_new_collection(
    args: argparse.Namespace,
    _parser: argparse.ArgumentParser,
) -> int:
    config_path = _config_path(args.config)
    approved_paths = _approved_collection_paths(
        [args.collection],
        [args.expected_root],
        command="plan-new-collection",
    )
    plan = plan_new_collection(
        args.collection,
        approved_paths[args.collection],
        args.contains,
        args.domain,
    )
    print("Planned new collection:")
    _print_resolved_collection(plan.planned)
    if plan.same_domain_counterpart is not None:
        print("Resolved existing counterpart:")
        _print_resolved_collection(plan.same_domain_counterpart)
    else:
        print(f"No deterministic counterpart: {plan.counterpart_note}.")

    registration_paths = required_sandbox_paths(
        knowledge_paths=[plan.planned.collection_path],
        include_qmd_state=True,
    )
    print("Sandbox write paths required before registration:")
    for path in registration_paths:
        print(f"  {path}")
    print(f"Codex config: {config_path}")
    _, _, state = load_sandbox_config_state(
        config_path,
        registration_paths,
    )
    if not state.missing_paths:
        print("Persistent config covers every pre-registration path.")
        print(
            "Use /status to verify effective paths before registering "
            "the collection."
        )
        return 0

    print("Missing pre-registration sandbox paths:")
    for path in state.missing_paths:
        print(f"  {path}")
    print("Session-only restart:")
    print(f"  {_session_access_command(state.missing_paths)}")
    print("Persistent setup after explicit approval:")
    print(f"  {_planned_persistent_access_command(plan, config_path)}")
    return EXIT_MISSING


def _handle_resolve_pair(
    args: argparse.Namespace,
    _parser: argparse.ArgumentParser,
) -> int:
    pair = resolve_knowledge_learning_pair(args.collection)
    print("Resolved knowledge/learning pair:")
    for collection in (pair.knowledge, pair.learning):
        _print_resolved_collection(collection)
    print("Persistent setup after explicit approval:")
    print(
        f"  {_persistent_access_command((pair.knowledge, pair.learning))}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler: CommandHandler = args.handler
    try:
        return handler(args, parser)
    except (
        CodexSandboxAccessError,
        CodexSandboxConfigError,
        KnowledgeBaseCatalogError,
    ) as exc:
        print(
            f"{args.error_prefix}: {exc}",
            file=sys.stderr,
        )
        return EXIT_UNSUPPORTED


if __name__ == "__main__":
    sys.exit(main())
