from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.operator.report_triage import ReadReportTriage
from studymate.application.operator.report_triage_ports import InvalidReportTriageSourceError
from studymate.domain.operator.report_triage import (
    TRIAGE_SOURCE_TOKEN_LIFETIME,
    ReportTriageSourceClaims,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.report_triage.store import REPORT_ID, TriageStore
from tests.unit.operator.report_triage.usecases_test import CODEC, context_reader
from tests.unit.operator.test_authorized_reads import HASHER


@pytest.mark.parametrize("change", ["actor", "grant", "session", "report", "expired", "tampered"])
def test_actual_source_token_is_bound_to_live_operator_session_report_and_time(change: str) -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    assert store.access is not None
    claims = ReportTriageSourceClaims(
        REPORT_ID,
        store.access.account_id,
        store.actor.session.id,
        store.access.version,
        None,
        b"d" * 32,
        NOW,
        NOW + TRIAGE_SOURCE_TOKEN_LIFETIME,
    )
    token = CODEC.encode_source(claims)
    access, actor_session, report, at = store.access, store.actor.session.id, REPORT_ID, NOW
    assert CODEC.decode_source(token, access, actor_session, report, at) == claims
    if change == "actor":
        access = replace(access, account_id=uuid4())
    elif change == "grant":
        access = replace(access, version=2)
    elif change == "session":
        actor_session = uuid4()
    elif change == "report":
        report = uuid4()
    elif change == "expired":
        at = claims.expires_at
    else:
        token = str(uuid4())
    with pytest.raises(InvalidReportTriageSourceError):
        CODEC.decode_source(token, access, actor_session, report, at)


async def test_unrepresentable_selected_evidence_is_audited_manual_path_without_source_token() -> (
    None
):
    store = TriageStore()
    store.assign_explicit_operator()
    assert store.preview is not None
    store.preview = replace(store.preview, context=None)
    view = await context_reader(store)(CREDENTIAL, REPORT_ID)
    assert view is not None
    assert view.source_token is None
    assert view.preview.context is None
    assert store.audit[-1].outcome.value == "read"
    actual = await ReadReportTriage(store, HASHER)(CREDENTIAL, REPORT_ID)
    assert actual is not None
    assert actual.triage is None
    assert not store.jobs


def test_same_text_under_changed_original_source_has_different_server_precondition() -> None:
    store = TriageStore()
    assert store.preview is not None
    original = store.preview.context
    assert original is not None
    changed = replace(original, report=replace(original.report, context_id=uuid4()))
    assert changed.evidence == original.evidence
    assert changed.evidence_digest != original.evidence_digest
