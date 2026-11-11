import json
from dataclasses import replace

import pytest

from studymate.application.requests.sources import context
from studymate.domain.discovery import DiscoveryMode
from studymate.infrastructure.requests.codec import (
    MAX_SNAPSHOT_BYTES,
    StoredRequestSnapshotError,
    decode_context,
    encode_context,
)
from tests.unit.requests.store import PEER, SENDER, Store


@pytest.mark.parametrize("mode", list(DiscoveryMode))
def test_immutable_actual_sources_roundtrip_with_all_private_content_and_versions(
    mode: DiscoveryMode,
) -> None:
    store = Store()
    snapshot = context(mode, store.sources[SENDER], store.sources[PEER])
    raw = encode_context(snapshot)
    assert decode_context(raw) == snapshot
    assert "Private synthetic" in raw
    assert "Private synthetic" not in repr(snapshot)
    assert len(raw.encode()) <= MAX_SNAPSHOT_BYTES


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b"\xff",
        "private\ud800",
        b" " * (MAX_SNAPSHOT_BYTES + 1),
        '{"schema_version":2,"context":{}}',
    ],
)
def test_corrupt_or_oversized_snapshots_fail_safely_without_private_error_context(
    raw: str | bytes,
) -> None:
    with pytest.raises(StoredRequestSnapshotError) as failed:
        decode_context(raw)
    assert "private" not in str(failed.value)
    assert failed.value.__suppress_context__ or (
        isinstance(raw, bytes) and len(raw) > MAX_SNAPSHOT_BYTES
    )


@pytest.mark.parametrize("field", ["unknown", "system", "model", "url"])
def test_snapshot_top_level_extra_keys_are_not_silently_accepted(field: str) -> None:
    store = Store()
    raw = encode_context(
        context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER])
    )
    with pytest.raises(StoredRequestSnapshotError, match="does not conform"):
        decode_context(raw[:-1] + ',"' + field + '":"PRIVATE"}')


def test_nested_goal_source_cannot_smuggle_extra_fields_or_boolean_revisions() -> None:
    store = Store()
    raw = encode_context(
        context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER])
    )
    for changed in (
        raw.replace('"version":1', '"version":true', 1),
        raw.replace('"subject_label":', '"unexpected":"PRIVATE","subject_label":', 1),
        raw.replace('"account_id":"' + str(SENDER) + '"', '"account_id":"' + str(PEER) + '"', 1),
    ):
        with pytest.raises(StoredRequestSnapshotError, match="does not conform"):
            decode_context(changed)


def test_snapshot_source_revision_and_content_are_not_replaced_by_live_state() -> None:
    store = Store()
    saved = context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER])
    encoded = encode_context(saved)
    source = store.sources[SENDER]
    assert source.setup.goal is not None
    changed_goal = source.setup.goal.goal.revise(
        replace(source.setup.goal.goal.content, context="Changed later"), store.clock
    )
    store.sources[SENDER] = replace(
        source, setup=replace(source.setup, goal=replace(source.setup.goal, goal=changed_goal))
    )
    assert decode_context(encoded) == saved
    assert context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER]) != saved
    assert json.loads(encoded)["schema_version"] == 1


def test_schema_revision_boolean_cannot_masquerade_as_integer_one() -> None:
    store = Store()
    raw = encode_context(
        context(DiscoveryMode.FIND_HELP, store.sources[SENDER], store.sources[PEER])
    )
    with pytest.raises(StoredRequestSnapshotError, match="does not conform"):
        decode_context(raw.replace('"schema_version":1', '"schema_version":true'))
