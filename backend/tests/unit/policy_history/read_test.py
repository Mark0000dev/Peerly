from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID

import pytest

from studymate.application.policy_history.read import (
    PolicyHistoryItem,
    PolicyHistoryPosition,
    ReadPolicyHistory,
)
from studymate.domain.registration import PolicyKind, PolicyReference, PolicyVersion
from studymate.presentation.policy_history.router import decode_position, encode_position


@dataclass(frozen=True, slots=True)
class Reader:
    rows: tuple[PolicyHistoryItem, ...]

    async def now(self) -> datetime:
        return datetime.now(UTC)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["Reader"]:
        yield self

    async def published_versions(
        self,
        kind: PolicyKind,
        before: PolicyHistoryPosition | None,
        limit: int,
        as_of: datetime,
    ) -> tuple[PolicyHistoryItem, ...]:
        return tuple(
            row
            for row in self.rows
            if row.reference.kind == kind
            and row.reference.published_at <= as_of
            and (
                before is None
                or (row.reference.published_at, row.reference.id) < (before.published_at, before.id)
            )
        )[:limit]


async def test_empty_published_history_is_truthful_empty_page() -> None:
    page = await ReadPolicyHistory(Reader(()))(PolicyKind.TERMS)
    assert page.items == ()
    assert page.next_position is None


async def test_bounded_lookahead_excludes_extra_row_from_response() -> None:
    at = datetime.now(UTC)
    rows = tuple(
        PolicyHistoryItem(
            PolicyReference(UUID(int=n), PolicyKind.TERMS, PolicyVersion(str(n)), at),
            "Terms",
        )
        for n in (3, 2, 1)
    )
    page = await ReadPolicyHistory(Reader(rows))(PolicyKind.TERMS, limit=2)
    assert page.items == rows[:2]
    assert page.next_position is not None
    assert page.next_position.published_at == at
    assert page.next_position.id == UUID(int=2)


@pytest.mark.parametrize("limit", [0, -1, 51, True])
async def test_invalid_limits_never_reach_storage(limit: int) -> None:
    with pytest.raises(ValueError, match="page size"):
        await ReadPolicyHistory(Reader(()))(PolicyKind.TERMS, limit=limit)


def test_cursor_is_canonical_and_scoped_to_document_kind() -> None:
    position = PolicyHistoryPosition(datetime.now(UTC), UUID(int=1), datetime.now(UTC))
    token = encode_position(PolicyKind.TERMS, position)
    assert decode_position(PolicyKind.TERMS, token) == position
    for invalid in (token + "=", "!", "a" * 257):
        with pytest.raises(ValueError, match="Invalid policy history cursor"):
            decode_position(PolicyKind.TERMS, invalid)
    with pytest.raises(ValueError, match="Invalid policy history cursor"):
        decode_position(PolicyKind.PRIVACY, token)


async def test_public_http_empty_history_and_safe_bounded_cursor_errors() -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from studymate.presentation.policy_history.router import policy_history_router

    app = FastAPI()
    app.include_router(policy_history_router(ReadPolicyHistory(Reader(()))))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/policies/terms/versions")
        assert result.status_code == HTTPStatus.OK
        assert result.json() == {"items": [], "next_cursor": None}
        assert result.headers["Cache-Control"] == "public, max-age=60"
        invalid = await client.get("/policies/terms/versions", params={"cursor": "private-invalid"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "private-invalid" not in invalid.text


async def test_future_server_anchor_cannot_be_used_for_public_pagination() -> None:
    from datetime import timedelta

    future = datetime.now(UTC) + timedelta(days=1)
    with pytest.raises(ValueError, match="Invalid policy history cursor"):
        await ReadPolicyHistory(Reader(()))(
            PolicyKind.TERMS, PolicyHistoryPosition(future, UUID(int=1), future)
        )
