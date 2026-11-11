from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
    RegistrationContext,
    RegistrationReceipt,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def reference(kind: PolicyKind) -> PolicyReference:
    return PolicyReference(
        UUID(int=1 if kind == PolicyKind.TERMS else 2),
        kind,
        PolicyVersion("synthetic-test-v1"),
        NOW,
    )


def context() -> RegistrationContext:
    return RegistrationContext(
        UUID(int=3),
        UUID(int=4),
        UUID(int=5),
        reference(PolicyKind.TERMS),
        reference(PolicyKind.PRIVACY),
        "Synthetic inline test notice.",
        NOW,
        NOW + timedelta(minutes=10),
    )


def test_notice_context_is_explicit_one_use_and_session_bound() -> None:
    issued = context()
    assert issued.can_complete(issued.account_id, issued.session_id, NOW)
    assert not issued.can_complete(UUID(int=9), issued.session_id, NOW)
    assert not issued.can_complete(issued.account_id, UUID(int=9), NOW)
    assert not issued.can_complete(issued.account_id, issued.session_id, issued.expires_at)
    assert not issued.can_complete(issued.account_id, issued.session_id, NOW - timedelta(seconds=1))
    completed = issued.complete(issued.account_id, issued.session_id, NOW)
    assert issued.completed_at is None
    assert completed.completed_at == NOW
    with pytest.raises(ValueError, match="unavailable"):
        completed.complete(issued.account_id, issued.session_id, NOW)
    receipt = RegistrationReceipt(
        UUID(int=6), issued.account_id, completed, NOW, "synthetic-intent"
    )
    assert receipt.context.notice_text == issued.notice_text
    assert receipt.context.terms == issued.terms
    assert receipt.context.privacy == issued.privacy
    assert "synthetic-intent" not in repr(receipt)


def test_authentication_or_context_issuance_cannot_fabricate_receipt() -> None:
    issued = context()
    with pytest.raises(ValueError, match="actual completion"):
        RegistrationReceipt(UUID(int=6), issued.account_id, issued, NOW, "synthetic-intent")
    completed = issued.complete(issued.account_id, issued.session_id, NOW)
    with pytest.raises(ValueError, match="actual completion"):
        RegistrationReceipt(UUID(int=6), UUID(int=99), completed, NOW, "synthetic-intent")


@pytest.mark.parametrize("version", ["", "spaces are invalid", "x" * 65, "\u212a"])
def test_document_version_is_explicit_and_bounded(version: str) -> None:
    with pytest.raises(ValueError, match="document version"):
        PolicyVersion(version)


def test_publication_requires_actual_content_and_aware_time() -> None:
    ref = reference(PolicyKind.TERMS)
    published = PublishedPolicy(
        ref, "Synthetic terms", "Synthetic test content, not production legal text."
    )
    assert published.title == "Synthetic terms"
    assert published.content not in repr(published)
    with pytest.raises(ValueError, match="actual content"):
        PublishedPolicy(ref, "", "body")
    with pytest.raises(ValueError, match="actual content"):
        PublishedPolicy(ref, "title", "")
    with pytest.raises(ValueError, match="timezone"):
        replace(ref, published_at=NOW.replace(tzinfo=None))


def test_context_rejects_wrong_kinds_future_publications_and_invalid_deadlines() -> None:
    issued = context()
    with pytest.raises(ValueError, match="kinds"):
        replace(issued, terms=issued.privacy)
    with pytest.raises(ValueError, match="unpublished"):
        replace(issued, terms=replace(issued.terms, published_at=NOW + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="valid deadline"):
        replace(issued, expires_at=NOW)
    with pytest.raises(ValueError, match="valid deadline"):
        replace(issued, notice_text=" ")
    with pytest.raises(ValueError, match="precedes"):
        replace(issued, completed_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(issued, completed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        issued.can_complete(issued.account_id, issued.session_id, NOW.replace(tzinfo=None))
