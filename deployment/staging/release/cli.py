"""Run one locked, source-bound internal staging promotion or explicit rollback."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
from dataclasses import asdict
from pathlib import Path

from deployment.staging.release.data import Object, RejectedError, load, obj, require, text
from deployment.staging.release.external_lifecycle import EXTERNAL_IMAGE, EXTERNAL_RELEASE
from deployment.staging.release.external_policy import policy, read_private
from deployment.staging.release.journal import Journal
from deployment.staging.release.portainer import Portainer
from deployment.staging.release.provenance import digest
from deployment.staging.release.providers import Github, Registry
from deployment.staging.release.release import (
    ASSETS,
    BACKEND,
    FRONTEND,
    RELEASE,
    SCHEMA,
    SOURCE,
    Image,
    Promotion,
    Snapshot,
    Target,
    merged_assets,
)
from deployment.staging.release.runtime import ObservationInputs, Runtime
from deployment.staging.release.transport import Http
from deployment.staging.release.validation import check_sha, container_id

MAX_ATTEMPT = 80
PRIVATE_DIRECTORY_MODE = stat.S_IRWXU


def private_write(path: Path, value: Object) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def secret(name: str) -> str:
    value = os.environ.get(name, "")
    require(
        bool(value) and "\r" not in value and "\n" not in value,
        "environment_input_missing_or_invalid",
    )
    return value


def previous_images(runtime: Runtime, registry: Registry, snapshot: Snapshot) -> dict[str, Image]:
    result = {}
    roles = [("backend", BACKEND), ("frontend", FRONTEND)]
    if runtime.external is not None:
        roles.append(("external", EXTERNAL_IMAGE))
    for role, key in roles:
        reference = snapshot.env()[key]
        image_role = "backend" if role == "external" else role
        manifest, config = registry.fetch(image_role, reference)
        inspected = runtime.portainer.image(reference)
        labels = obj(obj(load(config)["config"])["Labels"])
        sha = text(labels["org.opencontainers.image.revision"])
        check_sha(sha)
        require(
            labels.get("org.opencontainers.image.source") == SOURCE
            and reference.endswith("@" + digest(manifest))
            and obj(load(manifest)["config"])["digest"] == digest(config)
            and inspected["Id"] == digest(config),
            "previous_image_identity",
        )
        result[role] = Image(image_role, sha, reference, digest(config))
    return result


def run(args: argparse.Namespace) -> None:
    sha = text(args.sha)
    check_sha(sha)
    attempt = text(args.attempt)
    require(
        attempt.isascii() and attempt.replace("-", "").isalnum() and len(attempt) <= MAX_ATTEMPT,
        "attempt_identifier",
    )
    root = Path(secret("PEERLY_RELEASE_STATE_DIR"))
    metadata = root.lstat()
    require(
        root.is_absolute()
        and stat.S_ISDIR(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and stat.S_IMODE(metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
        "private_state_directory",
    )
    # This file is shared by every runner/manual parent deployment on the approved runner host.
    lock = os.open(root / "stack4.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args, sha, root / attempt)
    finally:
        os.close(lock)


def execute(args: argparse.Namespace, sha: str, directory: Path) -> None:
    blocker = directory.parent / "unresolved.json"
    if args.operation == "promote":
        require(
            not (directory.parent / ("rolled-back-" + sha + ".json")).exists(),
            "rolled_back_source_requires_forward_fix",
        )
    if blocker.exists():
        pending = load(blocker.read_bytes())
        require(
            args.operation in {"rollback", "reconcile"}
            and args.reconcile_attempt == pending["attempt"]
            and pending["sha"] == sha,
            "unresolved_attempt_requires_explicit_reconciliation",
        )
    directory.mkdir(mode=0o700)  # existing attempt always refuses, including crash/unknown PUT
    http = Http()
    github = Github(http, secret("PEERLY_GITHUB_TOKEN"))
    registry = Registry(http, secret("PEERLY_GHCR_USERNAME"), secret("PEERLY_GHCR_TOKEN"))
    operation = text(args.operation)
    if operation == "promote":
        github.source(sha)
    packages = {role: registry.package(github, role, sha) for role in ("backend", "frontend")}
    client = Portainer(http, secret("PEERLY_PORTAINER_ORIGIN"), secret("PEERLY_PORTAINER_API_KEY"))
    ai_id = secret("PEERLY_CANONICAL_AI_CONTAINER_ID")
    container_id(ai_id)
    journal = Journal(directory / "journal")
    inputs = ObservationInputs(
        secret("PEERLY_STAGING_METRICS_ORIGIN"),
        secret("PEERLY_STAGING_METRICS_PASSWORD"),
        secret("PEERLY_SMOKE_SESSION"),
        secret("PEERLY_SMOKE_ACCOUNT_ID"),
        ai_id,
        secret("PEERLY_STAGING_DATABASE_NAME"),
        (lambda: github.source(sha)) if operation == "promote" else (lambda: None),
        policy(),
    )
    runtime = Runtime(client, http, journal, packages, inputs)
    proofs: Object = {role: package.proof for role, package in packages.items()}
    promotion = Promotion(
        runtime,
        Target(4, 1, "peerly-staging"),
        packages["backend"].image,
        packages["frontend"].image,
        proofs,
    )
    promotion.external = runtime.external
    try:
        snapshot = promotion.read()
        private_write(
            directory / "before.private.json",
            {"stack": snapshot.stack, "content": snapshot.content},
        )
        if operation == "promote":
            baseline = runtime.evidence()
            previous = previous_images(runtime, registry, snapshot)
            if runtime.external is not None:
                require(
                    previous["external"] == runtime.external.image(), "external_previous_binding"
                )
            private_write(
                directory / "recovery.private.json",
                {
                    "sha": sha,
                    "baseline": baseline,
                    "previous": {role: asdict(image) for role, image in previous.items()},
                },
            )
            # Recheck moving main after artifact, registry and baseline acquisition, under lock.
            github.source(sha)
            if (
                snapshot.env()[BACKEND] == packages["backend"].image.reference
                and snapshot.env()[FRONTEND] == packages["frontend"].image.reference
                and (
                    runtime.external is None
                    or runtime.external.policy.upgrade_source != sha
                    or runtime.external.image() == packages["backend"].image
                )
            ):
                promotion.verify(snapshot, {r: p.image for r, p in packages.items()}, baseline)
                promotion.phase = "already_verified"
                final = snapshot
            else:
                private_write(
                    blocker, {"attempt": directory.name, "sha": sha, "operation": "promote"}
                )
                final = promotion.promote(packages["frontend"].release, baseline, previous)
                blocker.unlink()
                sync_directory(blocker.parent)
        else:
            final = recover(args, promotion, runtime, snapshot, directory)
        private_write(
            directory / "after.private.json", {"stack": final.stack, "content": final.content}
        )
        safe: Object = {
            "sha": sha,
            "phase": promotion.phase,
            "operation": operation,
            "stack_content_sha256": hashlib.sha256(final.content.encode()).hexdigest(),
            "images": {BACKEND: final.env()[BACKEND], FRONTEND: final.env()[FRONTEND]},
        }
        private_write(directory / "receipt.json", safe)
    finally:
        journal.close()


def recover(
    args: argparse.Namespace,
    promotion: Promotion,
    runtime: Runtime,
    snapshot: Snapshot,
    directory: Path,
) -> Snapshot:
    recovery = Path(text(args.recovery))
    require(
        recovery.is_absolute()
        and recovery.parent.parent == directory.parent
        and recovery.name == "recovery.private.json"
        and not recovery.is_symlink(),
        "recovery_scope",
    )
    original = load(recovery.read_bytes())
    require(
        original["sha"] == args.sha and args.compatible_schema == SCHEMA,
        "rollback_source_or_schema",
    )
    previous = {
        role: Image(**image_fields(obj(raw))) for role, raw in obj(original["previous"]).items()
    }
    blocker = directory.parent / "unresolved.json"
    pending = load(blocker.read_bytes()) if blocker.exists() else {}
    if args.operation == "reconcile":
        require(blocker.exists() and bool(args.reconcile_attempt), "reconciliation_required")
    before_raw = load((recovery.parent / "before.private.json").read_bytes())
    before = Snapshot(obj(before_raw["stack"]), text(before_raw["content"]))
    packages = runtime.packages
    approved = merged_assets(before.env()[ASSETS], packages["frontend"].release, text(args.sha))
    staged = before.changed(
        {BACKEND: packages["backend"].image.reference, ASSETS: approved, RELEASE: text(args.sha)}
    )
    final_candidate = staged.changed({FRONTEND: packages["frontend"].image.reference})
    rollback_candidate = before.changed({ASSETS: approved})
    candidates = [before, staged, final_candidate, rollback_candidate]
    require(
        runtime.external is not None or obj(original["baseline"])["external_delivery"] == "stopped",
        "external_recovery_acceptance_missing",
    )
    transition_directory, target = external_transition(
        runtime,
        directory.parent,
        recovery.parent,
        pending,
        {packages["backend"].image, previous.get("external")},
    )
    if target is not None:
        candidates.extend(
            candidate.changed({EXTERNAL_IMAGE: target.reference, EXTERNAL_RELEASE: target.sha})
            for candidate in list(candidates)
        )
    require(
        any(snapshot.same(candidate) for candidate in candidates), "unknown_reconciliation_state"
    )
    if runtime.external is not None:
        if not blocker.exists():
            private_write(
                blocker,
                {
                    "attempt": directory.name,
                    "sha": text(args.sha),
                    "operation": text(args.operation),
                },
            )
        snapshot = runtime.external.reconcile(
            promotion, snapshot, transition_directory, rollback=args.operation == "rollback"
        )
    if args.operation == "reconcile":
        known = {
            role: packages[role].image
            if snapshot.env()[key] == packages[role].image.reference
            else previous[role]
            for role, key in [("backend", BACKEND), ("frontend", FRONTEND)]
        }
        promotion.verify(snapshot, known, obj(original["baseline"]))
        promotion.phase = "reconcile_verified"
        final = snapshot
    else:
        if blocker.exists():
            private_write(directory / "reconciled-marker.json", load(blocker.read_bytes()))
        replacement = directory / "marker.json"
        private_write(
            replacement, {"attempt": directory.name, "sha": text(args.sha), "operation": "rollback"}
        )
        os.replace(replacement, blocker)
        sync_directory(blocker.parent)
        final = promotion.rollback(snapshot, previous, obj(original["baseline"]), SCHEMA)
    if args.operation == "rollback" or pending.get("operation") == "rollback":
        quarantine = directory.parent / ("rolled-back-" + text(args.sha) + ".json")
        if not quarantine.exists():
            private_write(quarantine, {"sha": text(args.sha), "attempt": directory.name})
    blocker.unlink()
    sync_directory(blocker.parent)
    return final


def external_transition(
    runtime: Runtime, root: Path, original: Path, pending: Object, allowed: set[Image | None]
) -> tuple[Path, Image | None]:
    directory = original
    if pending:
        candidate = root / text(pending["attempt"])
        require(candidate.parent == root, "external_recovery_attempt_scope")
        if (candidate / "external-before.private.json").exists():
            directory = candidate
    path = directory / "external-before.private.json"
    if runtime.external is None or not path.exists():
        return directory, None
    target = Image(**image_fields(obj(read_private(path)["target"])))
    require(
        target.sha in runtime.external.policy.compatible_sources and target in allowed,
        "external_recovery_compatibility",
    )
    return directory, target


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def image_fields(raw: Object) -> dict[str, str]:
    require(set(raw) == {"role", "sha", "reference", "config"}, "recovery_image")
    return {key: text(value) for key, value in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation", choices=["promote", "rollback", "reconcile"], default="promote"
    )
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--recovery", default="")
    parser.add_argument("--reconcile-attempt", default="")
    parser.add_argument("--compatible-schema", default="")
    try:
        run(parser.parse_args())
    except RejectedError:
        # No exception message/body/headers/session/env is emitted at this boundary.
        sys.stderr.write("release_rejected_inspect_private_attempt\n")
        return 1
    except (OSError, ValueError, KeyError, TimeoutError):
        sys.stderr.write("release_failed_or_uncertain_reconcile_before_retry\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
