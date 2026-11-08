from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from math import floor
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

from studymate.application.media.processing import MAX_SOURCE_BYTES, ImageFailure, InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    MediaUploadAccessExpiredError,
    UploadAccess,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef

MAX_UPLOAD_ACCESS_SECONDS = 900
READ_CHUNK_BYTES = 65536
MISSING_CODES = frozenset({"NoSuchKey", "NotFound", "404"})


class _UploadForm(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    url: str = Field(repr=False)
    fields: dict[str, str] = Field(repr=False)


def object_key(reference: MediaObjectRef) -> str:
    if reference.kind == MediaObjectKind.UPLOAD:
        return f"transport/{reference.upload_id}/source"
    name = "photo.jpg" if reference.kind == MediaObjectKind.DISPLAY else "original"
    return f"retained/{reference.upload_id}/{reference.attempt_id}/{name}"


@dataclass(frozen=True, slots=True)
class S3MediaStorage:
    client: S3Client = field(repr=False)
    bucket: str

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        lifetime = min(
            MAX_UPLOAD_ACCESS_SECONDS, floor((expires_at - datetime.now(UTC)).total_seconds())
        )
        if lifetime < 1:
            raise MediaUploadAccessExpiredError
        if reference.kind != MediaObjectKind.UPLOAD or content_type not in {
            "image/jpeg",
            "image/png",
        }:
            raise ValueError("Upload access must target a bounded JPEG/PNG transport object")
        try:
            raw = await self.client.generate_presigned_post(
                Bucket=self.bucket,
                Key=object_key(reference),
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, MAX_SOURCE_BYTES],
                ],
                ExpiresIn=lifetime,
            )
            form = _UploadForm.model_validate(raw)
        except (BotoCoreError, ClientError, ValidationError, TimeoutError) as error:
            raise MediaStorageUnavailableError from error
        return UploadAccess(form.url, tuple(sorted(form.fields.items())))

    async def read(self, reference: MediaObjectRef) -> bytes:
        try:
            async with asyncio.timeout(20):
                result = await self.client.get_object(
                    Bucket=self.bucket,
                    Key=object_key(reference),
                    Range=f"bytes=0-{MAX_SOURCE_BYTES}",
                )
                async with result["Body"] as stream:
                    if result["ContentLength"] > MAX_SOURCE_BYTES:
                        raise InvalidImageError(ImageFailure.TOO_LARGE)
                    data = bytearray()
                    while chunk := await stream.read(
                        min(READ_CHUNK_BYTES, MAX_SOURCE_BYTES + 1 - len(data))
                    ):
                        data.extend(chunk)
                        if len(data) > MAX_SOURCE_BYTES:
                            raise InvalidImageError(ImageFailure.TOO_LARGE)
                    if len(data) != result["ContentLength"]:
                        raise MediaStorageUnavailableError
                    return bytes(data)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in MISSING_CODES:
                raise MediaObjectMissingError from error
            raise MediaStorageUnavailableError from error
        except (BotoCoreError, TimeoutError) as error:
            raise MediaStorageUnavailableError from error

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        if reference.kind == MediaObjectKind.UPLOAD:
            raise ValueError("Retention must target an immutable processing attempt")
        try:
            async with asyncio.timeout(20):
                await self.client.put_object(
                    Bucket=self.bucket,
                    Key=object_key(reference),
                    Body=data,
                    ContentType=content_type,
                    IfNoneMatch="*",
                )
        except ClientError as error:
            # Existing attempt object is only success after byte identity is checked.
            if (
                error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                == HTTPStatus.PRECONDITION_FAILED
                and await self.read(reference) == data
            ):
                return
            raise MediaStorageUnavailableError from error
        except (BotoCoreError, TimeoutError) as error:
            raise MediaStorageUnavailableError from error

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        if reference.kind != MediaObjectKind.UPLOAD:
            raise ValueError("Retained business objects cannot be cleaned as transport")
        try:
            async with asyncio.timeout(20):
                await self.client.delete_object(Bucket=self.bucket, Key=object_key(reference))
        except (BotoCoreError, ClientError, TimeoutError) as error:
            raise MediaStorageUnavailableError from error
