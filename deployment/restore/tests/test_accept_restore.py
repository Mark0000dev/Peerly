"""Synthetic offline files only: no PostgreSQL, native command or provider invocation."""

import hashlib
import json
from pathlib import Path

import pytest
from deployment.restore import accept_restore as restore

IDENTITY = "11111111-1111-1111-1111-111111111111"
ATTEMPT = "22222222-2222-2222-2222-222222222222"
STEM = f"retained/{IDENTITY}/{ATTEMPT}/"
RENDITIONS = 2
PRIVATE = b"private-media-fixture"


def fixture(root: Path) -> tuple[Path, Path, Path]:
    media = root / "media"
    objects = []
    for name in ("original", "photo.jpg"):
        key = STEM + name
        file = media / key
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(PRIVATE)
        objects.append(
            {"key": key, "size": len(PRIVATE), "sha256": hashlib.sha256(PRIVATE).hexdigest()}
        )
    tables = {name: {"rows": 1, "sha256": "a" * 64} for name in restore.REQUIRED}
    data: dict[str, object] = {
        "format": 1,
        "heads": ["0059_human_reviews"],
        "tables": tables,
        "broken_relationships": 0,
        "unvalidated_constraints": 0,
        "disabled_triggers": 0,
        "objects": objects,
    }
    baseline, restored = root / "baseline.json", root / "restored.json"
    baseline.write_text(json.dumps(data))
    restored.write_text(json.dumps(data))
    return baseline, restored, media


def test_reads_actual_bytes_and_never_claims_genuine_full_restore(tmp_path: Path) -> None:
    baseline, restored, media = fixture(tmp_path)
    result = restore.verify(baseline, restored, media)
    assert result["verified_objects"] == RENDITIONS
    assert result["full_restore_proven"] is False
    assert "private-media" not in json.dumps(result)
    assert IDENTITY not in json.dumps(result)


@pytest.mark.parametrize(
    "operation", ["missing", "tamper", "truncate", "symlink", "directory_symlink"]
)
def test_missing_changed_or_linked_media_is_rejected(tmp_path: Path, operation: str) -> None:
    baseline, restored, media = fixture(tmp_path)
    original = media / STEM / "original"
    if operation == "directory_symlink":
        directory = original.parent
        saved = directory.with_name("elsewhere")
        directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
    else:
        original.unlink()
        if operation == "tamper":
            original.write_bytes(b"x" * len(PRIVATE))
        elif operation == "truncate":
            original.write_bytes(b"x")
        elif operation == "symlink":
            original.symlink_to(media / STEM / "photo.jpg")
    with pytest.raises((restore.RejectedError, OSError)):
        restore.verify(baseline, restored, media)


@pytest.mark.parametrize(
    "field", ["broken_relationships", "unvalidated_constraints", "disabled_triggers"]
)
def test_nonzero_actual_integrity_failures_never_pass(tmp_path: Path, field: str) -> None:
    baseline, restored, media = fixture(tmp_path)
    data = restore.load(restored)
    data[field] = 1
    restored.write_text(json.dumps(data))
    with pytest.raises(restore.RejectedError, match="relationships_or_constraints"):
        restore.verify(baseline, restored, media)


def test_equal_counts_with_changed_relational_rows_fail(tmp_path: Path) -> None:
    baseline, restored, media = fixture(tmp_path)
    data = restore.load(restored)
    tables = data["tables"]
    assert isinstance(tables, dict)
    tables["messages"] = {"rows": 1, "sha256": "b" * 64}
    restored.write_text(json.dumps(data))
    with pytest.raises(restore.RejectedError, match="snapshot_mismatch"):
        restore.verify(baseline, restored, media)


@pytest.mark.parametrize(
    "change", ["empty", "one_rendition", "duplicate", "traversal", "overbound"]
)
def test_partial_ambiguous_or_unbounded_inventory_fails(tmp_path: Path, change: str) -> None:
    baseline, restored, media = fixture(tmp_path)
    data = restore.load(restored)
    objects = data["objects"]
    assert isinstance(objects, list)
    if change == "empty":
        data["objects"] = []
    elif change == "one_rendition":
        data["objects"] = objects[:1]
    elif change == "duplicate":
        objects.append(objects[0])
    else:
        item = objects[0]
        assert isinstance(item, dict)
        if change == "traversal":
            item["key"] = "../private"
        else:
            item["size"] = restore.MAX_OBJECT_BYTES + 1
    restored.write_text(json.dumps(data))
    with pytest.raises(restore.RejectedError):
        restore.verify(baseline, restored, media)


def test_duplicate_json_keys_and_missing_product_tables_rejected(tmp_path: Path) -> None:
    baseline, restored, media = fixture(tmp_path)
    restored.write_text('{"format":1,"format":1}')
    with pytest.raises(restore.RejectedError, match="duplicate_json"):
        restore.load(restored)
    data = restore.load(baseline)
    data["tables"] = {}
    restored.write_text(json.dumps(data))
    with pytest.raises(restore.RejectedError, match="table_inventory"):
        restore.verify(baseline, restored, media)


def test_existing_destination_never_reused_and_generated_commands_are_scoped(
    tmp_path: Path,
) -> None:
    baseline, _restored, media = fixture(tmp_path)
    dump = tmp_path / "db.dump"
    dump.write_bytes(b"synthetic-archive-not-a-real-pg-dump")
    hashed = hashlib.sha256(dump.read_bytes()).hexdigest()
    destination = tmp_path / "owned-run"
    script = restore.plan(
        destination,
        source="source_database",
        port=55433,
        role="restore_drill",
        dump=dump,
        expected_sha256=hashed,
        baseline=baseline,
        media=media,
    )
    content = script.read_text()
    assert "--template=template0" in content
    assert "CONNECTION LIMIT 1" in content
    assert "--single-transaction" in content
    assert "--no-owner" in content
    assert "--no-privileges" in content
    assert "PGHOST=127.0.0.1" in content
    assert "--no-password" in content
    assert "env -i" in content
    assert "--clean" not in content
    assert "--create " not in content
    assert "--disable-triggers" not in content
    assert content.index("check-dump") < content.index("/usr/bin/createdb")
    assert content.index("created=1") > content.index("/usr/bin/createdb")
    assert "_test" in content
    with pytest.raises(FileExistsError):
        restore.plan(
            destination,
            source="source_database",
            port=55433,
            role="restore_drill",
            dump=dump,
            expected_sha256=hashed,
            baseline=baseline,
            media=media,
        )


@pytest.mark.parametrize("source", ["postgres; DROP DATABASE x", "--all", "", "UPPER"])
def test_database_identifiers_are_closed(source: str) -> None:
    with pytest.raises(restore.RejectedError, match="database_identity"):
        restore.target_name(source, "a" * 32)


def test_source_equals_target_refused_even_for_generated_identity() -> None:
    target = "peerly_restore_" + "a" * 32 + "_test"
    with pytest.raises(restore.RejectedError, match="database_identity"):
        restore.target_name(target, "a" * 32)


def test_wrong_dump_digest_rejected_before_creating_work_directory(tmp_path: Path) -> None:
    baseline, _restored, media = fixture(tmp_path)
    dump = tmp_path / "db.dump"
    dump.write_bytes(b"wrong")
    destination = tmp_path / "must-not-exist"
    with pytest.raises(restore.RejectedError, match="dump_digest"):
        restore.plan(
            destination,
            source="source",
            port=55433,
            role="drill",
            dump=dump,
            expected_sha256="0" * 64,
            baseline=baseline,
            media=media,
        )
    assert not destination.exists()


@pytest.mark.parametrize("port", [5432, 0, 65536])
def test_shared_default_or_invalid_endpoint_is_refused(tmp_path: Path, port: int) -> None:
    baseline, _restored, media = fixture(tmp_path)
    with pytest.raises(restore.RejectedError, match="isolated_endpoint"):
        restore.plan(
            tmp_path / "run",
            source="source",
            port=port,
            role="drill",
            dump=tmp_path / "absent",
            expected_sha256="a" * 64,
            baseline=baseline,
            media=media,
        )
    assert not (tmp_path / "run").exists()


def test_digest_rejects_oversized_file_and_symlink(tmp_path: Path) -> None:
    source = tmp_path / "file"
    source.write_bytes(b"12345")
    with pytest.raises(restore.RejectedError, match="file_bounds"):
        restore.digest(source, 4)
    linked = tmp_path / "link"
    linked.symlink_to(source)
    with pytest.raises(OSError, match="symbolic links"):
        restore.digest(linked, 8)
