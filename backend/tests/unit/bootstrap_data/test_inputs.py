import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from studymate.domain.bootstrap_data.inputs import (
    MAX_INPUT_BYTES,
    AuthoredSubject,
    BootstrapBatch,
    CatalogueManifest,
    CatalogueProvenance,
)
from studymate.presentation.bootstrap_data.inputs import (
    BootstrapInput,
    BootstrapInputError,
    load_input,
    parse_input,
    read_regular_file,
)
from tests.unit.bootstrap_data.data import SUBJECT_ID, batch, encoded
from tests.unit.identity_store import NOW


def test_closed_file_preserves_actual_policy_wording_and_normalizes_only_subject_labels() -> None:
    value = parse_input(encoded())
    assert value == batch()
    assert value.policies[0].content == "  PRIVATE_TERMS_BODY\r\n exact  "
    subject = AuthoredSubject(SUBJECT_ID, "  Synthetic   Subject ", ("  Synthetic   Alias ",))
    assert subject.name == "Synthetic Subject"
    assert subject.aliases == ("Synthetic Alias",)
    assert "PRIVATE_TERMS_BODY" not in repr(value)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":1,"schema_version":1,"policies":[],"catalogue":null}',
        b'{"schema_version":NaN}',
        b'{"schema_version":Infinity}',
        b'{"schema_version":1.0}',
        b'{"schema_version":true}',
        b"\xff",
        b"[]",
        b"{}",
        b'{"schema_version":1,"policies":[],"catalogue":null}',
        b'{"schema_version":1,"policies":[],"catalogue":null,"operator_grant":"PRIVATE"}',
    ],
)
def test_invalid_file_is_rejected_with_safe_finite_error(payload: bytes) -> None:
    with pytest.raises(BootstrapInputError) as caught:
        parse_input(payload)
    assert "PRIVATE" not in str(caught.value)
    assert "schema_version" not in str(caught.value)


@pytest.mark.parametrize(
    "fault", ["duplicates", "name_collision", "alias_collision", "alias_name", "policy_duplicate"]
)
def test_duplicate_source_identities_and_aliases_are_not_silently_coalesced(fault: str) -> None:
    original = batch()
    assert original.catalogue is not None
    subject = original.catalogue.subjects[0]

    def invalid() -> None:
        if fault == "duplicates":
            CatalogueManifest("test-v1", (subject, subject))
        elif fault == "name_collision":
            CatalogueManifest("test-v1", (subject, replace(subject, id=UUID(int=201))))
        elif fault == "alias_collision":
            replace(subject, aliases=("Alias", " alias "))
        elif fault == "alias_name":
            replace(subject, aliases=(subject.name,))
        else:
            BootstrapBatch((original.policies[0], original.policies[0]), None)

    with pytest.raises(ValueError, match=r"distinct|per kind"):
        invalid()


def test_manifest_hash_is_stable_across_subject_order_and_excludes_no_authored_fields() -> None:
    original = batch()
    assert original.catalogue is not None
    first = original.catalogue.subjects[0]
    second = replace(first, id=UUID(int=201), name="Another Subject", aliases=())
    left = CatalogueManifest("test-v2", (first, second))
    right = CatalogueManifest("test-v2", (second, first))
    assert left.sha256 == right.sha256
    assert left.canonical_json == right.canonical_json
    assert replace(left, version="test-v3").sha256 != left.sha256
    assert replace(left, subjects=(replace(first, aliases=()), second)).sha256 != left.sha256


async def test_file_loader_reads_only_explicit_regular_bounded_utf8_input(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.json"
    source.write_bytes(encoded())
    assert await load_input(source) == batch()
    with pytest.raises(BootstrapInputError):
        await load_input(tmp_path)
    with pytest.raises(BootstrapInputError):
        await load_input(tmp_path / "missing.json")


def test_schema_is_closed_and_has_no_actual_owner_policy_or_catalogue_defaults() -> None:
    schema = BootstrapInput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"schema_version", "policies", "catalogue"}
    assert "PRIVATE" not in json.dumps(schema)


@pytest.mark.parametrize("text", ["\ud800", "\x00private", "\x1bcontrol", "   "])
def test_authored_policy_rejects_invalid_unicode_controls_and_blank_text(text: str) -> None:
    original = batch().policies[0]
    with pytest.raises(ValueError, match="Authored text"):
        replace(original, content=text)


def test_explicit_source_size_count_and_digest_bounds(tmp_path: Path) -> None:
    with pytest.raises(BootstrapInputError):
        parse_input(b"")
    source = tmp_path / "oversized.json"
    source.write_bytes(b" " * (MAX_INPUT_BYTES + 1))
    with pytest.raises(BootstrapInputError):
        read_regular_file(source)
    with pytest.raises(ValueError, match="subject count"):
        CatalogueManifest("empty", ())
    with pytest.raises(ValueError, match="source digest"):
        CatalogueProvenance("bad", b"x" * 32, "{}", NOW, 1, 0)
