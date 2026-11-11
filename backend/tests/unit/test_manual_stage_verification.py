"""Owner-only helper parsing/provenance boundaries; no database or providers."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import re
import sys
from unittest.mock import patch
from uuid import UUID

import pytest
from deployment.backend import manual_stage_verification as helper

OCCURRENCE_KEY_LIMIT = 100
OPERATION = str(UUID(int=10))
FIRST = str(UUID(int=1))
SECOND = str(UUID(int=2))
CHALLENGE = str(UUID(int=3))
OTHER_CHALLENGE = str(UUID(int=4))
PRIVATE_EMAIL = "private-staging-student@mail.apu.edu.my"
PLACEHOLDER = "peerly-stage-00000000000000000000000000000002@mail.apu.edu.my"


def actual_entry() -> dict[str, object]:
    return {"account_id": FIRST, "email": PRIVATE_EMAIL, "challenge_id": CHALLENGE}


def placeholder_entry() -> dict[str, object]:
    return {"account_id": SECOND, "email": PLACEHOLDER, "challenge_id": None}


def payload(entries: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "operation_id": OPERATION,
        "performed_by": "owner-approved-staging",
        "entries": [actual_entry(), placeholder_entry()] if entries is None else entries,
    }


def encoded(value: object) -> bytes:
    return json.dumps(value).encode("utf-8")


def test_mixed_real_and_exact_account_derived_placeholder_are_sorted_and_private() -> None:
    value = payload([placeholder_entry(), actual_entry()])
    manifest = helper.parse_manifest(encoded(value))
    assert manifest.operation_id == UUID(OPERATION)
    assert tuple(entry.account_id for entry in manifest.entries) == (UUID(FIRST), UUID(SECOND))
    assert manifest.entries[0].challenge_id == UUID(CHALLENGE)
    assert manifest.entries[1].challenge_id is None
    assert manifest.entries[1].email == PLACEHOLDER
    assert helper.placeholder(UUID(SECOND)) == PLACEHOLDER
    assert re.fullmatch("^[0-9a-f]{64}$", manifest.fingerprint) is not None
    reordered_json = json.dumps(value, sort_keys=True, indent=2).encode()
    assert helper.parse_manifest(reordered_json).fingerprint == manifest.fingerprint
    assert PRIVATE_EMAIL not in repr(manifest)
    assert PLACEHOLDER not in repr(manifest)
    assert PRIVATE_EMAIL not in repr(manifest.entries[0])


def test_null_challenge_only_accepts_the_exact_derived_placeholder() -> None:
    wrong_emails = (PRIVATE_EMAIL, PLACEHOLDER.replace("02@", "01@"))
    for email in wrong_emails:
        entry = placeholder_entry()
        entry["email"] = email
        with pytest.raises(helper.ManualVerificationError) as rejected:
            helper.parse_manifest(encoded(payload([entry])))
        assert rejected.value.code == "invalid_placeholder"
    noncanonical = placeholder_entry()
    noncanonical["email"] = PLACEHOLDER.upper()
    with pytest.raises(helper.ManualVerificationError) as rejected:
        helper.parse_manifest(encoded(payload([noncanonical])))
    assert rejected.value.code == "noncanonical_email"


def test_duplicate_accounts_addresses_or_challenges_are_rejected() -> None:
    for field in ("account_id", "email", "challenge_id"):
        first = actual_entry()
        second: dict[str, object] = {
            "account_id": SECOND,
            "email": "other@mail.apu.edu.my",
            "challenge_id": OTHER_CHALLENGE,
        }
        second[field] = first[field]
        with pytest.raises(helper.ManualVerificationError) as rejected:
            helper.parse_manifest(encoded(payload([first, second])))
        assert rejected.value.code == "duplicate_target"


def test_unknown_root_and_entry_keys_and_wrong_types_are_rejected() -> None:
    invalid_roots: tuple[object, ...] = (
        None,
        [],
        "private",
        True,
        {**payload(), "unexpected": PRIVATE_EMAIL},
        {**payload(), "operation_id": 12},
        {**payload(), "entries": {}},
        {**payload(), "entries": []},
        {**payload(), "entries": [None]},
        {**payload(), "entries": [True]},
    )
    for value in invalid_roots:
        with pytest.raises(helper.ManualVerificationError):
            helper.parse_manifest(encoded(value))
    invalid_entries: tuple[dict[str, object], ...] = (
        {**actual_entry(), "unexpected": PRIVATE_EMAIL},
        {"account_id": FIRST, "email": PRIVATE_EMAIL},
        {**actual_entry(), "account_id": None},
        {**actual_entry(), "email": 12},
        {**actual_entry(), "challenge_id": True},
        {**actual_entry(), "challenge_id": []},
    )
    for entry in invalid_entries:
        with pytest.raises(helper.ManualVerificationError) as rejected:
            helper.parse_manifest(encoded(payload([entry])))
        assert rejected.value.code == "invalid_entry"


def test_operator_reference_is_bounded_nonprivate_and_not_an_email_or_free_text() -> None:
    for reference in (None, 1, True, "", "x" * 39, PRIVATE_EMAIL, "operator name", "a\nb"):
        value = payload()
        value["performed_by"] = reference
        with pytest.raises(helper.ManualVerificationError) as rejected:
            helper.parse_manifest(encoded(value))
        assert rejected.value.code == "invalid_performed_by"


def test_duplicate_json_keys_and_oversized_input_are_rejected() -> None:
    raw = b'{"operation_id":"x","operation_id":"y","performed_by":"owner","entries":[]}'
    with pytest.raises(helper.ManualVerificationError) as rejected:
        helper.parse_manifest(raw)
    assert rejected.value.code == "duplicate_json_key"
    with pytest.raises(helper.ManualVerificationError) as rejected:
        helper.parse_manifest(b" " * (helper.MAX_INPUT + 1))
    assert rejected.value.code == "input_too_large"
    with pytest.raises(helper.ManualVerificationError) as rejected:
        helper.parse_manifest(encoded(payload([actual_entry()] * (helper.MAX_ENTRIES + 1))))
    assert rejected.value.code == "invalid_entries"


def test_occurrence_encodes_real_or_placeholder_source_within_actual_storage_bound() -> None:
    value = payload()
    value["performed_by"] = "O" * 38
    manifest = helper.parse_manifest(encoded(value))
    actual, synthetic = manifest.entries
    real_key = helper.occurrence(manifest, actual)
    placeholder_key = helper.occurrence(manifest, synthetic)
    source = "c" + base64.urlsafe_b64encode(UUID(CHALLENGE).bytes).decode().rstrip("=")
    assert real_key == f"smv1:{UUID(OPERATION).hex}:{source}:{'O' * 38}"
    assert placeholder_key == f"smv1:{UUID(OPERATION).hex}:p:{'O' * 38}"
    assert len(real_key) == OCCURRENCE_KEY_LIMIT
    assert len(placeholder_key) <= OCCURRENCE_KEY_LIMIT
    assert real_key != placeholder_key
    assert PRIVATE_EMAIL not in real_key
    assert PLACEHOLDER not in placeholder_key


def test_wrong_database_cli_rejects_before_engine_creation_without_private_echo() -> None:
    output = io.StringIO()
    with (
        io.TextIOWrapper(io.BytesIO(encoded(payload())), encoding="utf-8") as input_stream,
        patch.object(sys, "argv", ["manual_stage_verification", "plan"]),
        patch.object(sys, "stdin", input_stream),
        patch.dict(
            os.environ,
            {
                "DATABASE_URL": (
                    "postgresql+asyncpg://synthetic-user:synthetic-password"
                    "@private.invalid/wrong_db"
                )
            },
            clear=True,
        ),
        patch.object(helper, "create_async_engine") as engine,
        contextlib.redirect_stdout(output),
    ):
        code = helper.main()
    assert code == 1
    engine.assert_not_called()
    assert json.loads(output.getvalue()) == {
        "status": "rejected",
        "code": "wrong_database_configuration",
    }
    for private in (PRIVATE_EMAIL, PLACEHOLDER, "synthetic-password", "private.invalid"):
        assert private not in output.getvalue()
