"""Application session scope remains canonical even when browser storage is lost."""

from datetime import datetime
from uuid import UUID

import pytest

from studymate.application.student_notifications.subscriptions import (
    LogoutInstallation,
    RetirementDisposition,
)
from tests.unit.student_notifications.test_installation_logout import (
    CREDENTIAL,
    NOW,
    Hasher,
    Store,
)


class SessionStore(Store):
    async def retire_installation(
        self,
        account_id: UUID,
        session_id: UUID,
        installation_id: UUID | None,
        at: datetime,
    ) -> bool:
        assert at == NOW
        assert account_id == self.account_id
        self.events.append("retire")
        if session_id != self.enrollment:
            return False
        self.enabled, self.retired = (False, True)
        return installation_id == self.installation


@pytest.mark.parametrize("supplied", [False, True])
async def test_current_session_retired_independent_of_optional_id(
    supplied: bool,
) -> None:
    store = SessionStore()
    result = await LogoutInstallation(store, Hasher())(
        CREDENTIAL, store.installation if supplied else None
    )
    assert store.revoked
    assert store.retired
    assert not store.enabled
    assert result == (
        RetirementDisposition.RETIRED if supplied else RetirementDisposition.UNCONFIRMED
    )
    assert (
        store.events.index("identity_locked")
        < store.events.index("retire")
        < store.events.index("revoke")
        < store.events.index("commit")
    )


async def test_unknown_id_ack_does_not_disable_session_retirement() -> None:
    from uuid import uuid4

    store = SessionStore()
    assert (
        await LogoutInstallation(store, Hasher())(CREDENTIAL, uuid4())
        == RetirementDisposition.UNCONFIRMED
    )
    assert store.revoked
    assert store.retired
    assert not store.enabled
