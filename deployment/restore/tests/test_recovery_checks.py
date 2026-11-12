import json
from pathlib import Path

import pytest
from deployment.restore.accept_restore import RejectedError
from deployment.restore.recovery_application import probe
from deployment.restore.recovery_checks import catalog, sequences, target_guard, verify
from sqlalchemy.ext.asyncio import create_async_engine

TARGET = "peerly_restore_" + "a" * 32 + "_test"


def metadata() -> dict[str, object]:
    return {
        "format": 2,
        "database": "peerly_staging",
        "heads": ["0060"],
        "invalid_indexes": 0,
        "entries": [
            {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
            {"kind": "index", "schema": "public", "name": "messages_pk", "sha256": "b" * 64},
            {"kind": "schema", "schema": "diagnostic", "name": "", "sha256": "c" * 64},
        ],
    }


def sequence(**changes: object) -> str:
    row: dict[str, object] = {
        "schema": "public",
        "name": "counter",
        "last": "12",
        "called": True,
        "increment": "1",
        "minimum": "1",
        "maximum": "9223372036854775807",
        "cycle": False,
        "owned": True,
        "edge": "12",
    }
    row.update(changes)
    return json.dumps(row) + "\n"


@pytest.mark.parametrize("target", ["peerly_staging", "shared_test", "postgres", TARGET + "x"])
def test_identity_rejects_shared_or_malformed(target: str) -> None:
    with pytest.raises(RejectedError):
        target_guard("peerly_staging", target)


def test_source_cannot_equal_target() -> None:
    with pytest.raises(RejectedError):
        target_guard(TARGET, TARGET)


def test_diagnostic_schema_and_index_changes_are_visible() -> None:
    expected = catalog(metadata(), ["0060"])
    changed = metadata()
    changed["entries"] = [
        {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
        {"kind": "index", "schema": "public", "name": "messages_pk", "sha256": "d" * 64},
    ]
    assert catalog(changed, ["0060"]) != expected


@pytest.mark.parametrize(
    "changes",
    [
        {"heads": ["0059"]},
        {"invalid_indexes": 1},
        {"invalid_indexes": False},
        {"format": True},
        {"entries": []},
    ],
)
def test_closed_catalog_failures(changes: dict[str, object]) -> None:
    value = metadata()
    value.update(changes)
    with pytest.raises(RejectedError):
        catalog(value, ["0060"])


def test_duplicate_definition_rejected() -> None:
    data = metadata()
    data["entries"] = [
        {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
    ] * 2
    with pytest.raises(RejectedError):
        catalog(data, ["0060"])


def test_sequence_next_value_safe_without_mutating_it() -> None:
    assert sequences(sequence(), {("public", "counter")}) == 1
    assert sequences(sequence(called=False, edge="11"), {("public", "counter")}) == 1
    assert (
        sequences(sequence(increment="-2", minimum="-100", edge="11"), {("public", "counter")}) == 1
    )
    assert sequences(sequence(called=False, edge=None), {("public", "counter")}) == 1
    assert sequences("", set()) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"called": False},
        {"edge": "13"},
        {"maximum": "12"},
        {"cycle": True},
        {"owned": False},
        {"increment": "0"},
        {"last": 12},
        {"called": 1},
        {"increment": "-1", "edge": "11"},
        {"last": "secret"},
    ],
)
def test_unsafe_sequences_fail(changes: dict[str, object]) -> None:
    with pytest.raises(RejectedError):
        sequences(sequence(**changes), {("public", "counter")})


@pytest.mark.parametrize("raw", ["", sequence() * 2, sequence(name="unexpected")])
def test_sequence_set_is_exact(raw: str) -> None:
    with pytest.raises(RejectedError):
        sequences(raw, {("public", "counter")})


def test_duplicate_json_and_bool_integer_rejected() -> None:
    with pytest.raises(RejectedError):
        sequences(
            sequence().replace('"last": "12"', '"last":"12","last":"13"'), {("public", "counter")}
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://127.0.0.1/shared_test",
        "postgresql+asyncpg://remote.invalid/" + TARGET,
        "postgresql+asyncpg://127.0.0.1/" + TARGET + "?host=remote.invalid",
    ],
)
async def test_application_engine_rejected_before_connection(url: str) -> None:
    # No DB is started or contacted. Invalid engine identity must fail before IO.
    engine = create_async_engine(url)
    try:
        with pytest.raises(RejectedError):
            await probe(engine, source="peerly_staging", target=TARGET)
    finally:
        await engine.dispose()


def test_catalog_mismatch_failure_uses_closed_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deployment.restore import recovery_checks

    expected = metadata()
    restored = metadata()
    restored.update(
        database=TARGET,
        entries=[
            {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
        ],
    )
    values: dict[str, dict[str, object]] = {
        "baseline": {"heads": ["0060"]},
        "source": expected,
        "restored": restored,
    }

    def loader(path: Path) -> dict[str, object]:
        return values[path.name]

    def inventory_stub(value: dict[str, object]) -> None:
        assert value == values["baseline"]

    monkeypatch.setattr(recovery_checks, "load", loader)
    monkeypatch.setattr(recovery_checks, "inventory", inventory_stub)
    with pytest.raises(RejectedError, match=r"^recovery_schema_mismatch$"):
        verify(
            tmp_path / "baseline", tmp_path / "source", tmp_path / "restored", tmp_path / "absent"
        )


def test_real_baseline_interface_and_empty_sequence_inventory(tmp_path: Path) -> None:
    from deployment.restore.accept_restore import REQUIRED

    key = "retained/" + "a" * 8 + "-aaaa-aaaa-aaaa-" + "a" * 12
    key += "/" + "b" * 8 + "-bbbb-bbbb-bbbb-" + "b" * 12
    baseline: dict[str, object] = {
        "format": 1,
        "heads": ["0060"],
        "tables": {name: {"rows": 0, "sha256": "a" * 64} for name in REQUIRED},
        "broken_relationships": 0,
        "unvalidated_constraints": 0,
        "disabled_triggers": 0,
        "objects": [
            {"key": key + suffix, "size": 1, "sha256": "b" * 64}
            for suffix in ("/original", "/photo.jpg")
        ],
    }
    source = metadata()
    source["entries"] = [
        {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
        *[
            {"kind": "relation", "schema": "public", "name": name, "sha256": "b" * 64}
            for name in REQUIRED
        ],
    ]
    restored = dict(source)
    restored["database"] = TARGET
    for name, value in (("baseline", baseline), ("source", source), ("restored", restored)):
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "sequences").write_text("")
    result = verify(*(tmp_path / name for name in ("baseline", "source", "restored", "sequences")))
    assert result["sequences_checked"] == 0
    assert result["full_restore_proven"] is False
    (tmp_path / "link").symlink_to(tmp_path / "sequences")
    with pytest.raises(OSError, match="Too many levels of symbolic links"):
        verify(*(tmp_path / name for name in ("baseline", "source", "restored", "link")))


@pytest.mark.parametrize("literal", ["'normal'", "'a,b]'", "'a''b'", "'ARRAY[x]::text[]'"])
def test_native_pg16_array_cast_roundtrip_is_canonical(literal: str) -> None:
    from deployment.restore.recovery_checks import definition_hash

    source = "CHECK ((kind)::text = ANY ((ARRAY[" + literal + "::character varying])::text[]))"
    restored = "CHECK ((kind)::text = ANY (ARRAY[(" + literal + "::character varying)::text]))"
    assert definition_hash(source) == definition_hash(restored)
    assert definition_hash(source) != definition_hash(source.replace("kind", "other"))


def test_cast_normalizer_preserves_other_semantics() -> None:
    from deployment.restore.recovery_checks import definition_hash

    checks = [
        "CHECK (x = 'a b')",
        "CHECK (x = 'ab')",
        "CHECK (x = 'a''b')",
        "CHECK (x = 'a')",
        "CHECK (x <> 'a')",
        "CHECK (x = NULL)",
        "CHECK (x = ANY ((ARRAY['a'::character varying(2)])::text[]))",
        "CHECK (x = ANY ((ARRAY['a'::character varying])::varchar[]))",
        "CHECK (x = ANY ((ARRAY[fn()])::text[]))",
    ]
    assert len({definition_hash(item) for item in checks}) == len(checks)
    assert definition_hash("CHECK (x = 'a b')") == definition_hash("CHECK  ( x = 'a b' )")
    # A string containing cast syntax remains a string, not a rewrite target.
    assert definition_hash(
        "CHECK (x = '(ARRAY[''a''::character varying])::text[]')"
    ) != definition_hash("CHECK (x = 'ARRAY[(''a''::character varying)::text]')")


def test_native_definition_hash_is_bound_before_normalization() -> None:
    value = metadata()
    value["entries"] = [
        {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
        {
            "kind": "constraint",
            "schema": "public",
            "name": "counter.check",
            "sha256": "b" * 64,
            "definition": "CHECK (id > 1)",
        },
    ]
    with pytest.raises(RejectedError, match="recovery_definition_hash"):
        catalog(value, ["0060"])


def test_old_catalog_format_cannot_be_relabelled() -> None:
    value = metadata()
    value["format"] = 1
    with pytest.raises(RejectedError, match="recovery_catalog"):
        catalog(value, ["0060"])
