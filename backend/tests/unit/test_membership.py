from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from studymate.domain.identity import StudentEmail
from studymate.domain.membership import (
    GOOGLE_ISSUER,
    AttemptOutcome,
    ChallengeState,
    EmailChallenge,
    GoogleIdentity,
    Membership,
    identity_capabilities,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
EMAIL = StudentEmail("tp@mail.apu.edu.my")


def challenge() -> EmailChallenge:
    return EmailChallenge(
        id=UUID(int=1),
        account_id=UUID(int=2),
        session_id=UUID(int=3),
        email=EMAIL,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        resend_at=NOW + timedelta(seconds=30),
    )


def test_google_subject_is_the_identity_not_an_email() -> None:
    identity = GoogleIdentity(GOOGLE_ISSUER, "12345")
    assert identity.subject == "12345"
    assert identity != GoogleIdentity(GOOGLE_ISSUER, "54321")


@pytest.mark.parametrize(
    ("issuer", "subject"),
    [
        ("https://evil.example", "123"),
        (GOOGLE_ISSUER, ""),
        (GOOGLE_ISSUER, "x" * 256),
    ],
)
def test_untrusted_or_invalid_identity_shape(issuer: str, subject: str) -> None:
    with pytest.raises(ValueError, match="Google"):
        GoogleIdentity(issuer, subject)


def test_fifth_wrong_attempt_locks_even_correct_code() -> None:
    original = challenge()
    current = original
    for _ in range(4):
        current, outcome = current.attempt(matches=False, at=NOW)
        assert outcome == AttemptOutcome.WRONG
    current, outcome = current.attempt(matches=False, at=NOW)
    assert outcome == AttemptOutcome.LOCKED
    assert current.state(NOW) == ChallengeState.LOCKED
    unchanged, outcome = current.attempt(matches=True, at=NOW)
    assert unchanged is current
    assert outcome == AttemptOutcome.LOCKED
    assert original.attempts == 0


def test_correct_code_consumes_once_without_creating_session() -> None:
    original = challenge()
    consumed, outcome = original.attempt(matches=True, at=NOW)
    assert outcome == AttemptOutcome.VERIFIED
    assert consumed.consumed_at == NOW
    assert consumed.account_id == original.account_id
    assert consumed.session_id == original.session_id
    assert consumed.state(NOW) == ChallengeState.CONSUMED
    assert consumed.attempt(matches=True, at=NOW) == (consumed, AttemptOutcome.UNAVAILABLE)
    assert not consumed.can_resend(NOW + timedelta(hours=1))


def test_expiry_and_resend_boundaries() -> None:
    original = challenge()
    assert original.state(original.expires_at - timedelta(microseconds=1)) == ChallengeState.ACTIVE
    assert original.attempt(matches=True, at=original.expires_at) == (
        original,
        AttemptOutcome.EXPIRED,
    )
    assert not original.can_resend(original.resend_at - timedelta(microseconds=1))
    assert original.can_resend(original.resend_at)
    superseded = original.supersede(original.resend_at)
    assert superseded.state(original.resend_at) == ChallengeState.SUPERSEDED
    assert superseded.attempt(matches=True, at=original.resend_at)[1] == AttemptOutcome.UNAVAILABLE
    assert not superseded.can_resend(original.resend_at)
    with pytest.raises(ValueError, match="superseded"):
        original.supersede(NOW)
    with pytest.raises(ValueError, match="precedes"):
        original.attempt(matches=True, at=NOW - timedelta(seconds=1))


@pytest.mark.parametrize("attempts", [-1, 6])
def test_invalid_attempt_counter(attempts: int) -> None:
    with pytest.raises(ValueError, match="attempt count"):
        replace(challenge(), attempts=attempts)


def test_invalid_deadlines_and_terminal_states() -> None:
    original = challenge()
    with pytest.raises(ValueError, match="deadlines"):
        replace(original, resend_at=original.expires_at)
    with pytest.raises(ValueError, match="precedes"):
        replace(original, consumed_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="consumed and superseded"):
        replace(original, consumed_at=NOW, superseded_at=NOW)
    with pytest.raises(ValueError, match="timezone"):
        replace(original, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        replace(original, consumed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        original.can_resend(NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        original.state(NOW.replace(tzinfo=None))


def test_membership_has_no_implicit_expiry_and_revocation_removes_capability() -> None:
    verified = Membership(EMAIL, NOW)
    assert verified.is_verified
    assert not replace(verified, revoked_at=NOW).is_verified
    with pytest.raises(ValueError, match="precedes"):
        replace(verified, revoked_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone"):
        replace(verified, verified_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        replace(verified, revoked_at=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("banned", [True, False])
@pytest.mark.parametrize("activation_complete", [True, False])
@pytest.mark.parametrize("membership", [None, Membership(EMAIL, NOW), Membership(EMAIL, NOW, NOW)])
def test_authentication_does_not_imply_membership_or_activation(
    banned: bool,
    activation_complete: bool,
    membership: Membership | None,
) -> None:
    capabilities = identity_capabilities(
        membership=membership,
        banned=banned,
        activation_complete=activation_complete,
    )
    verified = membership is not None and membership.is_verified
    assert capabilities.can_verify_student_email == (membership is None and not banned)
    assert capabilities.can_begin_onboarding == (verified and not banned)
    assert capabilities.can_use_student_features == (
        verified and not banned and activation_complete
    )
