from dataclasses import fields, replace
from uuid import uuid4

import pytest

from studymate.application.operator.data import (
    OperatorAccountDetail,
    OperatorMembershipSnapshot,
    OperatorRegistrationSnapshot,
)
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.media import PhotoRevision
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.profiles import DisplayName
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    RegistrationSurface,
)
from studymate.domain.study_context import (
    CustomSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubjects,
    StudyGoal,
)
from tests.unit.identity_store import NOW, IdentityStore
from tests.unit.operator.store import TARGET, target


def full_detail() -> OperatorAccountDetail:
    detail = target()
    membership = IdentityStore().actor.membership
    assert membership is not None
    summary = replace(detail.account, membership=OperatorMembershipSnapshot(TARGET, membership))
    registration = OperatorRegistrationSnapshot(
        uuid4(),
        TARGET,
        uuid4(),
        NOW,
        PolicyReference(uuid4(), PolicyKind.TERMS, PolicyVersion("actual-v1"), NOW),
        PolicyReference(uuid4(), PolicyKind.PRIVACY, PolicyVersion("actual-v1"), NOW),
        "Actual stored inline notice",
        RegistrationSurface.ONBOARDING_COMPLETION,
    )
    goal = StudyGoal(
        uuid4(), TARGET, 1, GoalContent(CustomSubjectRef("Private custom goal")), NOW, NOW
    )
    return replace(
        detail,
        account=summary,
        photo=PhotoRevision(TARGET, 1, uuid4(), NOW),
        goal=SavedGoal(goal, "Private custom goal"),
        help_subjects=SavedHelpSubjects(HelpRevision(TARGET, 1, HelpSubjects(), NOW), ()),
        registration=registration,
    )


def test_detail_links_only_actual_present_sources_without_counts_or_auth_secrets() -> None:
    detail = full_detail()
    assert detail.account.google_link is not None
    assert detail.registration is not None
    assert detail.goal is not None
    actual_ids = {
        detail.account.google_link.id,
        TARGET,
        detail.goal.goal.id,
        detail.registration.id,
    }
    assert {ref.id for ref in detail.links} == actual_ids
    assert "Private" not in repr(detail)
    assert "Actual stored" not in repr(detail)
    for cls in (
        type(detail),
        type(detail.account),
        type(detail.account.google_link),
        OperatorAudit,
    ):
        names = {entry.name for entry in fields(cls)}
        assert not names & {
            "secret_digest",
            "sealed_material",
            "code",
            "code_digest",
            "total_conversations",
            "google_email",
        }


def mismatched_detail(component: str) -> OperatorAccountDetail:
    original = full_detail()
    foreign = uuid4()
    if component == "profile":
        invalid_detail = (
            replace(original, profile=replace(original.profile, account_id=foreign))
            if original.profile is not None
            else original
        )
    elif component == "photo":
        invalid_detail = (
            replace(original, photo=replace(original.photo, account_id=foreign))
            if original.photo is not None
            else original
        )
    elif component == "goal":
        invalid_detail = (
            replace(
                original,
                goal=replace(original.goal, goal=replace(original.goal.goal, account_id=foreign)),
            )
            if original.goal is not None
            else original
        )
    elif component == "help":
        invalid_detail = (
            replace(
                original,
                help_subjects=replace(
                    original.help_subjects,
                    revision=replace(original.help_subjects.revision, account_id=foreign),
                ),
            )
            if original.help_subjects is not None
            else original
        )
    elif component == "registration":
        invalid_detail = (
            replace(original, registration=replace(original.registration, account_id=foreign))
            if original.registration is not None
            else original
        )
    elif component == "version":
        invalid_detail = replace(original, account=replace(original.account, profile_version=2))
    else:
        invalid_detail = replace(
            original,
            account=replace(original.account, display_name=DisplayName("Invented masked name")),
        )
    return invalid_detail


@pytest.mark.parametrize(
    "component", ["profile", "photo", "goal", "help", "registration", "version", "name"]
)
def test_detail_rejects_foreign_or_mismatched_stored_source(component: str) -> None:
    with pytest.raises(ValueError, match=r"foreign|actual source|actual stored"):
        mismatched_detail(component)


async def test_absent_stored_components_do_not_invent_links_identity_or_counts() -> None:
    original = target()
    minimal = replace(
        original.account,
        google_link=None,
        membership=None,
        profile_version=None,
        display_name=None,
        banned_at=None,
        deleted_at=None,
        hidden_at=None,
    )
    detail = OperatorAccountDetail(minimal, None, None, None, None, None, None, None)
    assert detail.links == ()
    assert detail.account.display_name is None
    assert detail.account.google_link is None


@pytest.mark.parametrize(
    "violation",
    [
        "google",
        "membership",
        "version",
        "orphan_name",
        "google_shape",
        "registration_kind",
        "registration_notice",
    ],
)
def test_source_projection_rejects_unrelated_identity_or_fabricated_registration(
    violation: str,
) -> None:
    def malformed_source() -> object:
        original = full_detail()
        if violation == "google":
            assert original.account.google_link is not None
            return replace(
                original.account,
                google_link=replace(original.account.google_link, account_id=uuid4()),
            )
        if violation == "membership":
            assert original.account.membership is not None
            return replace(
                original.account,
                membership=replace(original.account.membership, account_id=uuid4()),
            )
        if violation in {"version", "orphan_name"}:
            return replace(
                original.account, profile_version=True if violation == "version" else None
            )
        if violation == "google_shape":
            assert original.account.google_link is not None
            return replace(original.account.google_link, subject="")
        assert original.registration is not None
        if violation == "registration_kind":
            return replace(original.registration, terms=original.registration.privacy)
        return replace(original.registration, notice_text="")

    with pytest.raises(
        ValueError,
        match=r"another account|positive|actual stored|source identifiers|document|notice",
    ):
        malformed_source()
