"""Exact account-keyed sources for the three canonical saved profile-media families."""

from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest

from studymate.domain.operator.timeline import (
    OperatorEventFacts,
    OperatorEventKind,
    OperatorEventSource,
    OperatorSourceKind,
)
from studymate.infrastructure.operator.timeline_values import event_value
from studymate.presentation.operator.timeline_models import event_response
from tests.unit.operator.test_timeline_http import client
from tests.unit.operator.test_timeline_mapping import row_for
from tests.unit.operator.timeline_store import TimelineStore

FAMILIES = (
    (OperatorEventKind.PROFILE_SAVED, OperatorSourceKind.PROFILE),
    (OperatorEventKind.HELP_SAVED, OperatorSourceKind.HELP),
    (OperatorEventKind.PHOTO_PUBLISHED, OperatorSourceKind.PHOTO),
)


@pytest.mark.parametrize(("kind", "source_kind"), FAMILIES)
def test_new_family_has_only_exact_revision_source_and_empty_facts(
    kind: OperatorEventKind, source_kind: OperatorSourceKind
) -> None:
    row = row_for(kind)
    original = event_value(row)
    assert original.facts == OperatorEventFacts()
    assert original.sources == (
        OperatorEventSource(source_kind, row.account_id, row.account_id, version=1),
    )
    dto = event_response(original)
    assert dto.sources[0].kind == source_kind
    assert all(value is None for value in dto.facts.model_dump().values())
    with pytest.raises(ValueError, match="subject"):
        replace(
            original,
            sources=(
                *original.sources,
                OperatorEventSource(OperatorSourceKind.SUBJECT, uuid4(), None),
            ),
        )


@pytest.mark.parametrize(("kind", "source_kind"), FAMILIES)
@pytest.mark.parametrize("version", [None, 0, -1, True])
def test_revision_identity_never_comes_from_current_pointer_or_default(
    kind: OperatorEventKind, source_kind: OperatorSourceKind, version: int | None
) -> None:
    with pytest.raises(ValueError, match="positive revision"):
        OperatorEventSource(source_kind, uuid4(), uuid4(), version=version)
    row = row_for(kind)
    if kind == OperatorEventKind.PROFILE_SAVED:
        row.profile_version = version
    elif kind == OperatorEventKind.HELP_SAVED:
        row.help_version = version
    else:
        row.photo_version = version
    with pytest.raises(ValueError, match="positive revision"):
        event_value(row)


@pytest.mark.parametrize(("kind", "source_kind"), FAMILIES)
def test_saved_revision_source_requires_actual_same_account_key(
    kind: OperatorEventKind, source_kind: OperatorSourceKind
) -> None:
    owner = uuid4()
    with pytest.raises(ValueError, match="actual account"):
        OperatorEventSource(source_kind, uuid4(), owner, version=1)
    original = event_value(row_for(kind))
    with pytest.raises(ValueError, match="subject/kind"):
        replace(original, subject_account_id=owner)


@pytest.mark.parametrize(("kind", "source_kind"), FAMILIES)
async def test_new_kind_is_valid_http_filter_with_only_closed_revision_metadata(
    kind: OperatorEventKind,
    source_kind: OperatorSourceKind,
) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    event = event_value(row_for(kind))
    store.events = (event,)
    store.event_map = {event.id: event}
    async with client(store) as http:
        listing = await http.get("/api/v1/operator/events", params={"kind": kind.value})
        detail = await http.get(f"/api/v1/operator/events/{event.id}")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert len(listing.json()["events"]) == 1
    assert detail.json()["kind"] == kind.value
    assert detail.json()["sources"][0]["kind"] == source_kind.value
    assert detail.json()["sources"][0]["id"] == str(event.subject_account_id)
    assert detail.json()["sources"][0]["version"] == 1
    assert all(value is None for value in detail.json()["facts"].values())
    assert detail.headers["Cache-Control"] == "no-store"
    assert detail.headers["Referrer-Policy"] == "no-referrer"
    assert "query_fingerprint" not in detail.text
