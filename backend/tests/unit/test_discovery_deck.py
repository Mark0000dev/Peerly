from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from studymate.application.discovery.cursors import (
    DiscoveryCursor,
    DiscoveryView,
    decode_discovery_cursor,
    encode_discovery_cursor,
)
from studymate.application.discovery.deck import (
    DISCOVERY_PAGE_SIZE,
    CandidateSource,
    DiscoveryDeckReader,
    DiscoveryEmptyReason,
    ReadDiscoveryDeck,
)
from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_freshness import DiscoveryExposure
from studymate.domain.discovery_order import DiscoveryPosition
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.test_discovery_profiles import TARGET, source
from tests.unit.test_pass_use_cases import Store as PassStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        existing = PassStore()
        self.actor = existing.actor
        self.sources = existing.sources
        peer = self.sources[TARGET]
        peer = replace(
            peer, setup=replace(peer.setup, exposure=DiscoveryExposure(TARGET, NOW, NOW))
        )
        self.rows: tuple[CandidateSource, ...] = (
            CandidateSource(peer, DiscoveryPosition(False, 0, TARGET)),
        )
        self.has_people = False
        self.calls: list[tuple[DiscoveryView, DiscoveryCursor | None, datetime, int]] = []
        self.expire_on_query = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[DiscoveryDeckReader]:
        yield self

    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        return self.sources.get(account_id)

    async def latest_undo_pass(self, context: DiscoveryContext) -> PrivatePassRevision | None:
        assert context.account_id == self.actor.session.account_id
        return None

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        assert actor_id != target_id
        raise AssertionError("Deck uses bounded bulk authority, never per-person pair queries")

    async def candidates(
        self,
        context: DiscoveryContext,
        view: DiscoveryView,
        cursor: DiscoveryCursor | None,
        as_of: datetime,
        limit: int,
    ) -> tuple[CandidateSource, ...]:
        assert context.account_id == self.actor.session.account_id
        self.calls.append((view, cursor, as_of, limit))
        if self.expire_on_query:
            self.clock = self.actor.session.expires_at
        return self.rows

    async def has_context_people(self, context: DiscoveryContext, at: datetime) -> bool:
        assert context.account_id == self.actor.session.account_id
        assert at == self.clock
        return self.has_people


class CursorCodec:
    def encode(
        self, context: DiscoveryContext, view: DiscoveryView, cursor: DiscoveryCursor
    ) -> str:
        return encode_discovery_cursor(context, view, cursor)

    def decode(
        self, context: DiscoveryContext, view: DiscoveryView, token: str, now: datetime
    ) -> DiscoveryCursor:
        return decode_discovery_cursor(context, view, token, now)


def reader(store: Store) -> ReadDiscoveryDeck:
    return ReadDiscoveryDeck(store, Sha256SessionHasher(), CursorCodec())


def row(store: Store, value: int) -> CandidateSource:
    person = UUID(int=value)
    peer = source(person, store)
    help_subjects = store.sources[TARGET].setup.help_subjects
    assert help_subjects is not None
    help_subjects = replace(
        help_subjects, revision=replace(help_subjects.revision, account_id=person)
    )
    peer = replace(
        peer,
        setup=replace(
            peer.setup, help_subjects=help_subjects, exposure=DiscoveryExposure(person, NOW, NOW)
        ),
    )
    return CandidateSource(peer, DiscoveryPosition(False, 0, person))


async def test_deck_returns_declared_relevance_without_identity_or_fake_profile_view() -> None:
    store = Store()
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    assert len(result.people) == 1
    card = result.people[0]
    assert card.profile.account_id == TARGET
    assert card.match.reason.value == "can_help"
    assert card.match.reciprocal_subject_id is None
    assert result.empty_reason is None
    assert result.next_cursor is None
    assert "mail.apu.edu.my" not in repr(result)
    assert "Synthetic peer" not in repr(result)
    assert store.calls == [(DiscoveryView.CANDIDATES, None, NOW, DISCOVERY_PAGE_SIZE + 1)]


async def test_page_is_bounded_and_cursor_uses_last_scanned_position_and_fixed_anchor() -> None:
    store = Store()
    store.rows = tuple(row(store, value) for value in range(100, 100 + DISCOVERY_PAGE_SIZE + 1))
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    assert len(result.people) == DISCOVERY_PAGE_SIZE
    assert result.context is not None
    assert result.next_cursor is not None
    decoded = decode_discovery_cursor(
        result.context, DiscoveryView.CANDIDATES, result.next_cursor, NOW
    )
    assert decoded.position == store.rows[DISCOVERY_PAGE_SIZE - 1].position
    store.clock += timedelta(minutes=1)
    await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP, cursor=result.next_cursor)
    assert store.calls[-1][1] == decoded
    assert store.calls[-1][2] == NOW


@pytest.mark.parametrize("has_people", [False, True])
async def test_empty_reason_uses_actual_source_existence_not_fabricated_counts(
    has_people: bool,
) -> None:
    store = Store()
    store.rows = ()
    store.has_people = has_people
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    expected = (
        DiscoveryEmptyReason.EXHAUSTED if has_people else DiscoveryEmptyReason.NO_RELEVANT_PEOPLE
    )
    assert result.empty_reason == expected


async def test_missing_selected_mode_context_never_silently_changes_mode_or_goal() -> None:
    store = Store()
    result = await reader(store)(CREDENTIAL, DiscoveryMode.OFFER_HELP)
    assert result.context is None
    assert result.empty_reason == DiscoveryEmptyReason.CONTEXT_REQUIRED
    assert not store.calls


@pytest.mark.parametrize(
    "state", ["hidden", "paused", "expired", "missing_exposure", "irrelevant", "self"]
)
async def test_stale_bulk_source_is_never_disclosed(state: str) -> None:
    store = Store()
    peer = store.rows[0].source
    setup = peer.setup
    if state == "hidden":
        assert setup.lifecycle is not None
        setup = replace(setup, lifecycle=setup.lifecycle.with_visibility(hidden=True, at=NOW))
    elif state == "paused":
        setup = replace(setup, exposure=DiscoveryExposure(TARGET, NOW, NOW, NOW))
    elif state == "expired":
        past = NOW - timedelta(days=31)
        setup = replace(setup, exposure=DiscoveryExposure(TARGET, past, past))
    elif state == "missing_exposure":
        setup = replace(setup, exposure=None)
    elif state == "irrelevant":
        setup = replace(setup, help_subjects=None)
    else:
        peer = store.sources[store.actor.session.account_id]
        setup = peer.setup
    peer = replace(peer, setup=setup)
    store.rows = (CandidateSource(peer, DiscoveryPosition(False, 0, setup.account_id)),)
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    assert not result.people


async def test_final_session_expiry_and_overlarge_adapter_page_fail() -> None:
    store = Store()
    store.expire_on_query = True
    with pytest.raises(UnauthenticatedError):
        await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    store = Store()
    store.rows = tuple(row(store, value) for value in range(100, 100 + DISCOVERY_PAGE_SIZE + 2))
    with pytest.raises(RuntimeError, match="bounded page"):
        await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)


async def test_missing_activation_or_own_source_is_denied() -> None:
    store = Store()
    store.actor = replace(store.actor, activation_complete=False)
    with pytest.raises(StudentActionDeniedError):
        await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)

    store = Store()
    del store.sources[store.actor.session.account_id]
    with pytest.raises(StudentActionDeniedError):
        await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)


async def test_own_exposure_pause_does_not_become_a_browsing_ban_or_confirmation() -> None:
    store = Store()
    actor_id = store.actor.session.account_id
    own = store.sources[actor_id]
    paused = DiscoveryExposure(actor_id, NOW, NOW, NOW)
    store.sources[actor_id] = replace(own, setup=replace(own.setup, exposure=paused))
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    assert result.people
    assert store.sources[actor_id].setup.exposure == paused


async def test_passed_view_is_explicit_and_uses_same_actual_context() -> None:
    store = Store()
    result = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP, DiscoveryView.PASSED)
    assert result.people
    assert store.calls[0][0] == DiscoveryView.PASSED
    assert result.context is not None
    assert result.context.account_id == store.actor.session.account_id


def test_candidate_position_cannot_refer_to_another_person() -> None:
    store = Store()
    with pytest.raises(ValueError, match="scoped source"):
        CandidateSource(store.rows[0].source, DiscoveryPosition(False, 0, UUID(int=999)))
