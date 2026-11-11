from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import ValidationError

from studymate.application.discovery.cursors import DiscoveryView
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
)
from studymate.presentation.discovery_models import (
    ChangePassRequest,
    context_response,
    page_response,
    scope_value,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.test_discovery_deck import Store, reader


@pytest.mark.parametrize("mode", list(DiscoveryMode))
def test_context_roundtrip_never_accepts_a_client_actor(mode: DiscoveryMode) -> None:
    value = DiscoveryContext(
        UUID(int=1),
        mode,
        None if mode == DiscoveryMode.OFFER_HELP else UUID(int=2),
        None if mode == DiscoveryMode.OFFER_HELP else 1,
        1 if mode == DiscoveryMode.OFFER_HELP else None,
    )
    public = context_response(value)
    assert "account_id" not in public.model_dump()
    assert scope_value(public).bind(value.account_id) == value
    with pytest.raises(ValidationError, match="validation error"):
        type(public).model_validate({**public.model_dump(), "account_id": str(UUID(int=9))})


@pytest.mark.parametrize(
    "change", ["passed_string", "version_bool", "undo_pass", "actor", "foreign_fields"]
)
def test_private_pass_shape_is_strict(change: str) -> None:
    context: dict[str, object] = {
        "mode": "find_help",
        "goal_id": str(UUID(int=2)),
        "goal_version": 1,
    }
    body: dict[str, object] = {"context": context, "passed": True, "expected_version": 0}
    if change == "passed_string":
        body["passed"] = "true"
    elif change == "version_bool":
        body["expected_version"] = True
    elif change == "undo_pass":
        body["undo"] = True
    elif change == "actor":
        body["account_id"] = str(UUID(int=9))
    else:
        context["help_version"] = 1
    with pytest.raises(ValidationError, match="validation error"):
        ChangePassRequest.model_validate(body)


async def test_card_output_is_narrow_and_never_fabricates_a_disclosure_reference() -> None:
    store = Store()
    value = await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP)
    response = page_response(value)
    card = response.people[0]
    assert set(card.model_dump()) == {
        "id",
        "version",
        "display_name",
        "about",
        "photo",
        "relevance",
        "own_pass",
    }
    assert card.relevance.subject_label == "Synthetic subject"
    assert card.own_pass.version == 0
    assert card.own_pass.changed_at is None
    assert "mail.apu.edu.my" not in response.model_dump_json()
    assert "Synthetic peer" not in repr(response)
    photo = store.rows[0].source.setup.photo
    assert photo is not None
    assert str(photo.upload_id) not in response.model_dump_json()


async def test_reciprocal_label_uses_exact_candidate_goal_source() -> None:
    store = Store()
    actor_id = store.actor.session.account_id
    own = store.sources[actor_id]
    reciprocal = UUID(int=60)
    own_help = SavedHelpSubjects(
        HelpRevision(actor_id, 1, HelpSubjects((HelpSubject(reciprocal),)), NOW),
        ("Synthetic reciprocal",),
    )
    store.sources[actor_id] = replace(own, setup=replace(own.setup, help_subjects=own_help))
    row = store.rows[0]
    peer = row.source
    assert peer.setup.goal is not None
    saved = peer.setup.goal
    updated_goal = replace(
        saved,
        goal=replace(
            saved.goal, content=replace(saved.goal.content, subject=CanonicalSubjectRef(reciprocal))
        ),
        subject_label="Synthetic reciprocal",
    )
    peer = replace(peer, setup=replace(peer.setup, goal=updated_goal))
    store.rows = (replace(row, source=peer),)
    result = page_response(await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP))
    assert result.people[0].relevance.reciprocal_subject_id == reciprocal
    assert result.people[0].relevance.reciprocal_subject_label == "Synthetic reciprocal"


async def test_empty_passed_view_reports_no_available_passed_people() -> None:
    store = Store()
    store.rows = ()
    result = page_response(
        await reader(store)(CREDENTIAL, DiscoveryMode.FIND_HELP, DiscoveryView.PASSED)
    )
    assert result.empty_reason is not None
    assert result.empty_reason.value == "no_available_passed_people"
