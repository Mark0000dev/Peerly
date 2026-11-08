from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.goal_ports import (
    OperatorGoalFilters,
    OperatorGoalHistoryHead,
    OperatorGoalHistoryPosition,
    OperatorGoalRootPosition,
    OperatorGoalState,
)
from studymate.application.operator.goals import ReadOperatorGoalHistory, ReadOperatorGoals
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.goals import OPERATOR_GOAL_PAGE_SIZE
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.goal_cursors import FernetOperatorGoalCursorCodec
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.goal_store import (
    ACTIVE_GOAL,
    COMPLETED_GOAL,
    RAW_CONTEXT,
    RAW_KEY,
    RAW_LABEL,
    RAW_TOPIC,
    GoalStore,
    revision,
    root,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorGoalCursorCodec.from_key(b"g" * 32)


def roots(store: GoalStore) -> ReadOperatorGoals:
    return ReadOperatorGoals(store, HASHER, FINGERPRINTER, CODEC)


def history(store: GoalStore) -> ReadOperatorGoalHistory:
    return ReadOperatorGoalHistory(store, HASHER, CODEC)


async def test_goal_metadata_and_raw_history_need_only_operator_authority() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    page = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    assert page is not None
    assert {row.id for row in page.goals} == {ACTIVE_GOAL, COMPLETED_GOAL}
    assert not hasattr(page.goals[0], "topic")
    actual = await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    assert actual is not None
    assert tuple(row.version for row in actual.revisions) == (3, 2, 1)
    assert actual.revisions[0].saved_at < actual.revisions[-1].saved_at
    assert actual.revisions[0].subject_label == RAW_LABEL
    assert actual.revisions[0].topic == RAW_TOPIC
    assert actual.revisions[0].topic_match_key == RAW_KEY
    assert actual.revisions[0].context == RAW_CONTEXT
    assert RAW_CONTEXT not in repr(actual)
    audit = store.audit[-1]
    ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET)
    assert audit.action == OperatorAction.READ_ACCOUNT
    assert audit.requested == ref
    assert audit.results == (ref,)


async def test_missing_account_and_missing_child_do_not_falsify_container_audit() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    assert await history(store)(CREDENTIAL, TARGET, uuid4()) is None
    inspected = store.audit[-1]
    assert inspected.outcome == OperatorAuditOutcome.READ
    assert inspected.results == (OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET),)
    unknown = uuid4()
    assert await history(store)(CREDENTIAL, unknown, ACTIVE_GOAL) is None
    missing_account_audit = store.audit[-1]
    assert missing_account_audit.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing_account_audit.results
    assert await roots(store)(CREDENTIAL, unknown, OperatorGoalFilters()) is None
    store.roots = {}
    page = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    assert page is not None
    assert page.goals == ()
    assert page.anchor_created_at is None
    assert page.anchor_goal_id is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ


async def test_foreign_goal_is_child404_after_real_parent_read() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    store.roots[ACTIVE_GOAL] = replace(store.roots[ACTIVE_GOAL], account_id=uuid4())
    assert await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ
    assert store.audit[-1].requested == OperatorResourceRef(OperatorResourceKind.ACCOUNT, TARGET)


async def test_actual_root_filters_halfopen_time_and_future_metadata_are_truthful() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    active = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(OperatorGoalState.ACTIVE))
    ended = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(OperatorGoalState.COMPLETED))
    assert active is not None
    assert ended is not None
    assert tuple(row.id for row in active.goals) == (ACTIVE_GOAL,)
    assert tuple(row.id for row in ended.goals) == (COMPLETED_GOAL,)
    created = store.roots[ACTIVE_GOAL].created_at
    lower = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(created_from=created))
    upper = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(created_before=created))
    assert lower is not None
    assert lower.goals
    assert upper is not None
    assert upper.goals == ()
    future = replace(root(uuid4()), created_at=NOW + timedelta(days=1))
    store.roots[future.id] = future
    page = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    assert page is not None
    assert page.goals[0] == future
    assert page.anchor_created_at == future.created_at
    assert page.observed_at < future.created_at


async def test_root_keyset_bounds_new_higher_keys_but_metadata_changes_require_refresh() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    store.roots = {
        UUID(int=index): replace(
            root(UUID(int=index), completed=True), created_at=NOW + timedelta(minutes=index)
        )
        for index in range(1, OPERATOR_GOAL_PAGE_SIZE + 3)
    }
    first = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    assert first is not None
    assert len(first.goals) == OPERATOR_GOAL_PAGE_SIZE
    assert first.next_cursor is not None
    new = replace(root(uuid4()), created_at=NOW + timedelta(days=2))
    store.roots[new.id] = new
    store.roots[UUID(int=1)] = replace(store.roots[UUID(int=1)], current_version=7)
    second = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(), first.next_cursor)
    assert second is not None
    assert tuple(row.id for row in second.goals) == (UUID(int=2), UUID(int=1))
    assert second.goals[-1].current_version == store.roots[UUID(int=1)].current_version
    assert second.next_cursor is None
    assert second.anchor_goal_id == first.anchor_goal_id
    with pytest.raises(InvalidOperatorCursorError):
        await roots(store)(
            CREDENTIAL, TARGET, OperatorGoalFilters(OperatorGoalState.COMPLETED), first.next_cursor
        )
    refreshed = await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    assert refreshed is not None
    assert refreshed.goals[0] == new


async def test_history_uses_all_stored_versions_independent_current_pointer() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    latest = OPERATOR_GOAL_PAGE_SIZE + 2
    store.revisions[ACTIVE_GOAL] = tuple(revision(version) for version in range(1, latest + 1))
    first = await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    assert first is not None
    assert first.anchor_version == latest
    assert len(first.revisions) == OPERATOR_GOAL_PAGE_SIZE
    assert first.goal.current_version < first.anchor_version
    assert first.next_cursor is not None
    store.revisions[ACTIVE_GOAL] += (revision(latest + 1),)
    second = await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.anchor_version == latest
    assert second.next_cursor is None


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_goal_inspection_never_infers_role_or_overrides_actor_lifecycle(state: str) -> None:
    store = GoalStore()
    if state != "absent":
        store.assign_explicit_operator()
    if state == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif state == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if state in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    with pytest.raises(error):
        await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("failure", ["audit", "expiry_query", "expiry_audit"])
@pytest.mark.parametrize("reading_history", [False, True])
async def test_goal_reads_fail_closed_on_audit_or_final_session(
    failure: str, reading_history: bool
) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    operation = (
        history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
        if reading_history
        else roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    )
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await operation
    assert not store.audit


@pytest.mark.parametrize("fault", ["owner", "duplicate", "ascending", "filter", "excess"])
async def test_goal_roots_validate_actual_owned_ordered_bounded_metadata(fault: str) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    one = store.roots[ACTIVE_GOAL]
    two = replace(one, id=UUID(int=1))
    store.root_rows = {
        "owner": (replace(one, account_id=uuid4()),),
        "duplicate": (one, one),
        "ascending": (two, one),
        "filter": (store.roots[COMPLETED_GOAL],),
        "excess": tuple(one for _ in range(OPERATOR_GOAL_PAGE_SIZE + 2)),
    }[fault]
    with pytest.raises(RuntimeError, match="Goal root source"):
        await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters(OperatorGoalState.ACTIVE))
    assert not store.audit


@pytest.mark.parametrize(
    "fault", ["owner", "goal", "duplicate", "ascending", "above_anchor", "excess"]
)
async def test_goal_history_validates_exact_owner_goal_version_order(fault: str) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    one = revision(1)
    store.revision_rows = {
        "owner": (replace(one, account_id=uuid4()),),
        "goal": (replace(one, goal_id=uuid4()),),
        "duplicate": (one, one),
        "ascending": (one, revision(2)),
        "above_anchor": (revision(4),),
        "excess": tuple(one for _ in range(OPERATOR_GOAL_PAGE_SIZE + 2)),
    }[fault]
    with pytest.raises(RuntimeError, match=r"Goal.*source"):
        await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    assert not store.audit


async def test_goal_account_head_and_history_cursor_cannot_forge_ownership_or_future_version() -> (
    None
):
    store = GoalStore()
    store.assign_explicit_operator()
    store.account_override = uuid4()
    with pytest.raises(RuntimeError, match="another requested account"):
        await roots(store)(CREDENTIAL, TARGET, OperatorGoalFilters())
    with pytest.raises(RuntimeError, match="another requested account"):
        await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    store.account_override = None
    store.head_override = OperatorGoalHistoryHead(root(uuid4()), 3)
    with pytest.raises(RuntimeError, match="another actual owner or goal"):
        await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL)
    store.head_override = None
    scope = OperatorCursorScope(store.actor.session.account_id, 1)
    token = CODEC.encode_history(scope, TARGET, ACTIVE_GOAL, OperatorGoalHistoryPosition(4, 2))
    with pytest.raises(InvalidOperatorCursorError):
        await history(store)(CREDENTIAL, TARGET, ACTIVE_GOAL, token)


@pytest.mark.parametrize("change", ["actor", "grant", "account", "goal", "tamper", "oversized"])
def test_goal_history_cursor_bound_to_actual_actor_role_account_and_goal(change: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    account, goal = uuid4(), uuid4()
    position = OperatorGoalHistoryPosition(5, 2)
    token = CODEC.encode_history(scope, account, goal, position)
    assert CODEC.decode_history(scope, account, goal, token) == position
    if change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif change == "account":
        account = uuid4()
    elif change == "goal":
        goal = uuid4()
    elif change == "tamper":
        token = str(uuid4())
    else:
        token = "x" * 1025
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, account, goal, token)


@pytest.mark.parametrize("change", ["actor", "grant", "account", "filter"])
def test_root_cursor_is_bound_to_account_filter_scope(change: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    account = uuid4()
    digest = b"d" * 32
    position = OperatorGoalRootPosition(NOW, UUID(int=5), NOW, UUID(int=2))
    token = CODEC.encode_roots(scope, account, digest, position)
    assert CODEC.decode_roots(scope, account, digest, token) == position
    if change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif change == "account":
        account = uuid4()
    else:
        digest = b"f" * 32
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_roots(scope, account, digest, token)


@pytest.mark.parametrize(
    ("anchor", "before"),
    [("0", "1"), ("1", "2"), ("+2", "1"), ("2", "+1"), ("false", "1"), ("2147483648", "1")],
)
def test_goal_version_cursor_rejects_authenticated_but_invalid_source_bounds(
    anchor: str, before: str
) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    goal = uuid4()
    token = encode_cursor(
        CODEC.history,
        (
            "operator-goal-history-v1",
            str(scope.account_id),
            "1",
            str(TARGET),
            str(goal),
            anchor,
            before,
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, TARGET, goal, token)


def test_raw_goal_never_revalidates_current_content_or_cross_timestamps() -> None:
    raw = replace(
        revision(1),
        subject_label=" ",
        topic="x" * 200,
        context="c" * 500,
        topic_match_key=" UNNORMALIZED ß ",
        saved_at=NOW - timedelta(days=20),
        completed_at=NOW + timedelta(days=1),
    )
    assert raw.subject_label == " "
    assert raw.context == "c" * 500
    assert raw.topic_match_key == " UNNORMALIZED ß "
    assert raw.saved_at < root().created_at
    with pytest.raises(ValueError, match="bounded source version"):
        replace(root(), current_version=0)
    with pytest.raises(ValueError, match="bounded source version"):
        replace(raw, version=0)
    with pytest.raises(ValueError, match="positive source version"):
        OperatorGoalHistoryHead(root(), 0)
    with pytest.raises(ValueError, match="metadata anchor"):
        OperatorGoalRootPosition(NOW, UUID(int=1), NOW, UUID(int=2))
    with pytest.raises(ValueError, match="version anchor"):
        OperatorGoalHistoryPosition(2, 3)
    with pytest.raises(ValueError, match="half-open"):
        OperatorGoalFilters(created_from=NOW, created_before=NOW)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorGoalCursorCodec.from_key(b"short")
    with pytest.raises(ValueError, match="query HMAC"):
        CODEC.encode_roots(
            OperatorCursorScope(uuid4(), 1),
            TARGET,
            b"short",
            OperatorGoalRootPosition(NOW, uuid4(), NOW - timedelta(days=1), uuid4()),
        )
