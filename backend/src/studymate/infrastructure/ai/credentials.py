"""Single-account credential handoff, independent of disposable job history.

No login/refresh request is made here. A version-specific codec must validate only
credential fields and the owner-provisioned account binding; it is not JWT signature
verification. Production CLI/codec/tool isolation compatibility remains external.
"""

import asyncio
import fcntl
import hashlib
import os
import stat
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from studymate.application.ai.ports import AiExecutorError
from studymate.domain.ai.jobs import Failure
from studymate.infrastructure.ai.lifecycle import settle_cleanup
from studymate.infrastructure.ai.process import (
    CredentialStateUncertainError,
    TerminationUncertainError,
)

MAX_CREDENTIAL_BYTES = 65_536
MAX_JOURNAL_BYTES = 4096
PRIVATE_MASK = 0o077
PRIVATE_DIRECTORY_MODE = 0o700


@dataclass(frozen=True, slots=True)
class CredentialDocument:
    account_binding: str = field(repr=False)
    encoded: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.account_binding or not 0 < len(self.encoded) <= MAX_CREDENTIAL_BYTES:
            raise ValueError("Bounded account-bound credential document required")


class SubscriptionCredentialCodec(Protocol):
    def validate(self, encoded: bytes) -> CredentialDocument:
        """Reject unknown/private-history/API-key fields; return credential-only bytes.

        Account binding compares trusted provisioned cache metadata, not decoded JWT
        claims treated as authenticated identity. No network or token refresh here.
        """
        ...


class _Journal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    destination: str = Field(min_length=1, max_length=2048)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _directory(path: Path) -> int:
    if not path.is_absolute() or ".." in path.parts or path.parts[1:2] in {("home",), ("root",)}:
        raise ValueError("Dedicated absolute non-home credential directory required")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = following
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.geteuid() or metadata.st_mode & PRIVATE_MASK:
            raise ValueError("Credential directory must be private and owned by the runtime")
        return descriptor
    except (OSError, ValueError):
        os.close(descriptor)
        raise


async def validate_private_runtime_directory(path: Path) -> None:
    """Validate existing owned0700 directory metadata only, never enumerate/read files.

    Every path component is opened relative to its predecessor with O_NOFOLLOW.
    Parent must preserve these dedicated mounts between validation and CLI launch.
    """

    def validate() -> None:
        descriptor = _directory(path)
        try:
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != PRIVATE_DIRECTORY_MODE:
                raise ValueError("Runtime directory must have mode0700")
        finally:
            os.close(descriptor)

    await asyncio.to_thread(validate)


def _read(directory: int, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & PRIVATE_MASK
            or not 0 < metadata.st_size <= limit
        ):
            raise ValueError("Credential file must be private, regular and bounded")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            encoded = stream.read(limit + 1)
        if not 0 < len(encoded) <= limit:
            raise ValueError("Credential file exceeds limit")
        return encoded
    finally:
        os.close(descriptor)


def _write(directory: int, name: str, encoded: bytes) -> None:
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    try:
        with os.fdopen(os.dup(descriptor), "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _atomic(directory: int, name: str, encoded: bytes) -> None:
    temporary = f".handoff-{uuid4().hex}"
    try:
        _write(directory, temporary, encoded)
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)


def _exists(directory: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


@dataclass(slots=True)
class _Lease:
    resources: ExitStack = field(repr=False)
    source: int
    destination: int
    journal: _Journal = field(repr=False)


@dataclass(frozen=True, slots=True)
class DedicatedCredentialCache:
    directory: Path = field(repr=False)
    expected_account: str = field(repr=False)
    codec: SubscriptionCredentialCodec = field(repr=False)
    workspaces_root: Path = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not self.directory.is_absolute()
            or not self.workspaces_root.is_absolute()
            or self.directory.is_relative_to(self.workspaces_root)
            or self.workspaces_root.is_relative_to(self.directory)
        ):
            raise ValueError("Credential cache and workspaces require separate dedicated roots")

    def _destination(self, destination: Path) -> None:
        if (
            not destination.is_relative_to(self.workspaces_root)
            or ".." in destination.parts
            or destination.name != "auth"
            or not destination.parent.name.startswith("peerly-ai-")
        ):
            raise ValueError("Credential destination must be a dedicated job auth directory")

    def _document(self, encoded: bytes) -> CredentialDocument:
        document = self.codec.validate(encoded)
        if document.account_binding != self.expected_account:
            raise ValueError("Credential account binding changed")
        return document

    def _source(self, resources: ExitStack) -> int:
        directory = _directory(self.directory)
        resources.callback(os.close, directory)
        lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        resources.callback(os.close, lock)
        metadata = os.fstat(lock)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & PRIVATE_MASK
        ):
            raise ValueError("Invalid credential lock file")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return directory

    def _stage(self, destination: Path) -> _Lease:
        self._destination(destination)
        with ExitStack() as resources:
            source = self._source(resources)
            if _exists(source, "active.json"):
                raise ValueError("Unfinished credential handoff requires confirmed-stop recovery")
            original = _read(source, "auth.json", MAX_CREDENTIAL_BYTES)
            document = self._document(original)
            target = _directory(destination)
            resources.callback(os.close, target)
            # Exclusive create prevents replacing another job's credentials.
            _write(target, "auth.json", document.encoded)
            journal = _Journal(
                destination=str(destination), digest=hashlib.sha256(original).hexdigest()
            )
            try:
                _atomic(source, "active.json", journal.model_dump_json().encode())
            except OSError:
                if _exists(source, "active.json"):
                    raise CredentialStateUncertainError from None
                os.unlink("auth.json", dir_fd=target)
                raise
            return _Lease(resources.pop_all(), source, target, journal)

    def _checkpoint(self, lease: _Lease) -> None:
        original = _read(lease.source, "auth.json", MAX_CREDENTIAL_BYTES)
        candidate = self._document(
            _read(lease.destination, "auth.json", MAX_CREDENTIAL_BYTES)
        ).encoded
        # A completed replace followed by a crash/fsync failure may already have won.
        if original != candidate:
            if hashlib.sha256(original).hexdigest() != lease.journal.digest:
                raise ValueError("Credential source changed during handoff")
            _atomic(lease.source, "auth.json", candidate)
        os.unlink("active.json", dir_fd=lease.source)
        os.fsync(lease.source)
        os.unlink("auth.json", dir_fd=lease.destination)

    def _finish(self, lease: _Lease, *, confirmed_stopped: bool) -> None:
        try:
            if confirmed_stopped:
                self._checkpoint(lease)
            # Otherwise keep the journal/staged cache for trusted stopped recovery.
        finally:
            lease.resources.close()

    async def validate_ready(self) -> None:
        def validate() -> None:
            with ExitStack() as resources:
                source = self._source(resources)
                if _exists(source, "active.json"):
                    raise CredentialStateUncertainError
                self._document(_read(source, "auth.json", MAX_CREDENTIAL_BYTES))

        try:
            await asyncio.to_thread(validate)
        except (OSError, ValueError):
            raise AiExecutorError(Failure.AUTH) from None

    @asynccontextmanager
    async def lease(self, destination: Path) -> AsyncIterator[None]:
        stage = asyncio.create_task(asyncio.to_thread(self._stage, destination))
        try:
            active = await asyncio.shield(stage)
        except asyncio.CancelledError:
            active = await settle_cleanup(stage)
            finishing_cancelled = asyncio.create_task(
                asyncio.to_thread(self._finish, active, confirmed_stopped=True)
            )
            await settle_cleanup(finishing_cancelled)
            raise
        except (OSError, ValueError):
            raise AiExecutorError(Failure.AUTH) from None
        stopped = True
        try:
            yield
        except TerminationUncertainError:
            stopped = False
            raise
        finally:
            finishing = asyncio.create_task(
                asyncio.to_thread(self._finish, active, confirmed_stopped=stopped)
            )
            try:
                try:
                    await asyncio.shield(finishing)
                except asyncio.CancelledError:
                    await settle_cleanup(finishing)
                    raise
            except (OSError, ValueError):
                raise CredentialStateUncertainError from None

    async def recover_stopped(self, *, confirmed_stopped: bool) -> Path:
        if not confirmed_stopped:
            raise TerminationUncertainError("Credential recovery requires confirmed physical stop")
        recovering = asyncio.create_task(asyncio.to_thread(self._recover))
        try:
            try:
                return await asyncio.shield(recovering)
            except asyncio.CancelledError:
                await settle_cleanup(recovering)
                raise
        except (OSError, ValueError):
            raise CredentialStateUncertainError from None

    def _recover(self) -> Path:
        with ExitStack() as resources:
            source = self._source(resources)
            try:
                journal = _Journal.model_validate_json(
                    _read(source, "active.json", MAX_JOURNAL_BYTES)
                )
            except ValidationError:
                raise ValueError("Invalid credential handoff journal") from None
            destination = Path(journal.destination)
            self._destination(destination)
            target = _directory(destination)
            resources.callback(os.close, target)
            lease = _Lease(ExitStack(), source, target, journal)
            self._checkpoint(lease)
            return destination
