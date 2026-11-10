"""Synthetic fixtures only; runtime never imports or applies these values."""

import json
from uuid import UUID

from studymate.domain.bootstrap_data.inputs import (
    AuthoredPolicy,
    AuthoredSubject,
    BootstrapBatch,
    CatalogueManifest,
)
from studymate.domain.registration import PolicyKind, PolicyVersion

SUBJECT_ID = UUID(int=200)


def batch() -> BootstrapBatch:
    return BootstrapBatch(
        (
            AuthoredPolicy(
                PolicyKind.TERMS,
                PolicyVersion("test-v1"),
                "Synthetic Terms",
                "  PRIVATE_TERMS_BODY\r\n exact  ",
            ),
            AuthoredPolicy(
                PolicyKind.PRIVACY,
                PolicyVersion("test-v1"),
                "Synthetic Privacy",
                "PRIVATE_PRIVACY_BODY",
            ),
        ),
        CatalogueManifest(
            "test-v1", (AuthoredSubject(SUBJECT_ID, "Synthetic Subject", ("Synthetic Alias",)),)
        ),
    )


def encoded() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "policies": [
                {
                    "kind": value.kind.value,
                    "version": value.version.value,
                    "title": value.title,
                    "content": value.content,
                }
                for value in batch().policies
            ],
            "catalogue": {
                "version": "test-v1",
                "subjects": [
                    {
                        "id": str(SUBJECT_ID),
                        "name": "Synthetic Subject",
                        "aliases": ["Synthetic Alias"],
                    }
                ],
            },
        }
    ).encode()
