from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from studymate.domain.identity import Session, StudentEmail

ISSUED = datetime(2026, 11, 7, tzinfo=UTC)
LIFETIME = timedelta(days=7)


def session() -> Session:
    return Session(UUID(int=1), UUID(int=2), ISSUED, ISSUED + LIFETIME)


def test_email_canonicalisation_preserves_alias_distinctions() -> None:
    email = StudentEmail("  TP.Name+Study@MAIL.APU.EDU.MY  ")
    assert email.value == "tp.name+study@mail.apu.edu.my"
    assert email != StudentEmail("tp.name@mail.apu.edu.my")
    assert email != StudentEmail("tpname+study@mail.apu.edu.my")
    assert email.value not in repr(email)


@pytest.mark.parametrize(
    "address",
    [
        "",
        "@mail.apu.edu.my",
        "student@gmail.com",
        "student@apu.edu.my",
        "student@sub.mail.apu.edu.my",
        "student@mail.apu.edu.my.evil.example",
        "student@@mail.apu.edu.my",
        "student name@mail.apu.edu.my",
        "student\nname@mail.apu.edu.my",
        "üser@mail.apu.edu.my",
        "\u212aelvin@mail.apu.edu.my",
        '"student"@mail.apu.edu.my',
        ".student@mail.apu.edu.my",
        "student.@mail.apu.edu.my",
        "student..name@mail.apu.edu.my",
        f"{'a' * 65}@mail.apu.edu.my",
    ],
)
def test_email_rejects_invalid_or_noninstitutional_address(address: str) -> None:
    with pytest.raises(ValueError, match="institutional"):
        StudentEmail(address)


def test_maximum_local_part_length_is_valid() -> None:
    assert StudentEmail(f"{'a' * 64}@mail.apu.edu.my").value.startswith("a" * 64)


def test_session_active_interval_is_half_open() -> None:
    stored = session()
    assert not stored.is_active(ISSUED - timedelta(microseconds=1))
    assert stored.is_active(ISSUED)
    assert stored.is_active(stored.expires_at - timedelta(microseconds=1))
    assert not stored.is_active(stored.expires_at)
    assert not stored.is_active(stored.expires_at + timedelta(days=1))
    same_instant = ISSUED.astimezone(timezone(timedelta(hours=8)))
    assert stored.is_active(same_instant)


def test_revocation_is_immutable_and_cannot_be_extended_or_restored() -> None:
    original = session()
    revoked_at = ISSUED + timedelta(minutes=1)
    revoked = original.revoke(revoked_at)
    assert original.revoked_at is None
    assert original.is_active(revoked_at)
    assert revoked.revoked_at == revoked_at
    assert not revoked.is_active(revoked_at)
    assert not revoked.is_active(revoked_at + timedelta(seconds=1))
    assert revoked.revoke(revoked_at + timedelta(minutes=2)) is revoked


@pytest.mark.parametrize("expiry", [ISSUED, ISSUED - timedelta(seconds=1)])
def test_expiry_must_follow_issuance(expiry: datetime) -> None:
    with pytest.raises(ValueError, match="expiry"):
        Session(UUID(int=1), UUID(int=2), ISSUED, expiry)


def test_revocation_cannot_precede_issuance() -> None:
    earlier = ISSUED - timedelta(seconds=1)
    with pytest.raises(ValueError, match="revocation"):
        session().revoke(earlier)
    with pytest.raises(ValueError, match="revocation"):
        Session(UUID(int=1), UUID(int=2), ISSUED, ISSUED + LIFETIME, earlier)


def test_naive_timestamps_are_rejected_at_all_boundaries() -> None:
    naive = ISSUED.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone"):
        Session(UUID(int=1), UUID(int=2), naive, ISSUED + LIFETIME)
    with pytest.raises(ValueError, match="timezone"):
        Session(UUID(int=1), UUID(int=2), ISSUED, naive)
    with pytest.raises(ValueError, match="timezone"):
        Session(UUID(int=1), UUID(int=2), ISSUED, ISSUED + LIFETIME, naive)
    with pytest.raises(ValueError, match="timezone"):
        session().is_active(naive)
    with pytest.raises(ValueError, match="timezone"):
        session().revoke(naive)
