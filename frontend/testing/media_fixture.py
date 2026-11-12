"""Controlled storage boundary for real SQL photo UI integration; never external S3."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from email import policy
from email.parser import BytesParser
from uuid import UUID

from studymate.application.media.storage import MediaObjectMissingError, UploadAccess
from studymate.config import MediaConfiguration
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind, MediaObjectRef


class ControlledMedia:
    def __init__(self) -> None:
        self.objects: dict[MediaObjectRef, bytes] = {}
        self.accesses: dict[UUID, MediaObjectRef] = {}

    @asynccontextmanager
    async def open(
        self, _configuration: MediaConfiguration
    ) -> AsyncIterator["ControlledMedia"]:
        yield self

    async def upload_access(
        self, reference: MediaObjectRef, _content_type: str, _expires_at: datetime
    ) -> UploadAccess:
        self.accesses[reference.upload_id] = reference
        return UploadAccess(
            f"https://127.0.0.1:8769/uploads/{reference.upload_id}",
            (("key", str(reference.upload_id)), ("policy", "fixture-policy")),
        )

    async def read(self, reference: MediaObjectRef) -> bytes:
        if reference not in self.objects:
            raise MediaObjectMissingError
        return self.objects[reference]

    async def retain(
        self, reference: MediaObjectRef, data: bytes, _content_type: str
    ) -> None:
        if reference.kind == MediaObjectKind.UPLOAD or reference in self.objects:
            raise ValueError("Invalid retained fixture object")
        self.objects[reference] = data

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        if reference.kind != MediaObjectKind.UPLOAD:
            raise ValueError("Cannot remove retained fixture media")
        self.objects.pop(reference, None)

    def accept(self, upload_id: UUID, content_type: str, body: bytes) -> None:
        if upload_id not in self.accesses or len(body) > MAX_PHOTO_BYTES + 65536:
            raise ValueError("Unknown or oversized fixture transfer")
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        parts = list(message.iter_parts())
        if [part.get_param("name", header="content-disposition") for part in parts] != [
            "key",
            "policy",
            "file",
        ]:
            raise ValueError("Invalid native multipart fixture transfer")
        if (
            parts[0].get_content() != str(upload_id)
            or parts[1].get_content() != "fixture-policy"
        ):
            raise ValueError("Invalid controlled upload fields")
        data = parts[2].get_payload(decode=True)
        if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_PHOTO_BYTES:
            raise ValueError("Invalid fixture file")
        self.objects[self.accesses[upload_id]] = data
