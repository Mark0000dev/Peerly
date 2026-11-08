from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.domain.message_reports import (
    MessageImageRef,
    MessageImageReport,
    MessageImageReportContext,
)
from studymate.domain.reports import ReportCategory
from tests.unit.identity_store import NOW
from tests.unit.safety.message_reports.store import Store


@pytest.mark.parametrize("version", [0, True])
def test_image_reference_requires_actual_positive_revision(version: int) -> None:
    with pytest.raises(ValueError, match="positive READY"):
        MessageImageRef(uuid4(), version, uuid4())


@pytest.mark.parametrize("fault", ["outside", "self", "text"])
def test_context_retains_actual_peer_image_evidence(fault: str) -> None:
    store = Store()
    assert store.source is not None
    source = store.source
    reporter, at = store.actor.session.account_id, NOW
    if fault == "outside":
        reporter = uuid4()
    elif fault == "self":
        reporter = source.author_id
    elif fault == "text":
        source = replace(source, image=None)
    with pytest.raises(ValueError, match=r"report|context|attachment|Report"):
        MessageImageReportContext(uuid4(), reporter, source, at)


def test_source_author_is_actual_conversation_participant() -> None:
    store = Store()
    assert store.source is not None
    with pytest.raises(ValueError, match="participant"):
        replace(store.source, author_id=uuid4())


@pytest.mark.parametrize("fault", ["actor", "other"])
def test_report_preserves_owner_time_and_existing_comment_rules(fault: str) -> None:
    store = Store()
    assert store.source is not None
    context = MessageImageReportContext(uuid4(), store.actor.session.account_id, store.source, NOW)
    actor, at, category = context.reporter_id, NOW, ReportCategory.SPAM
    if fault == "actor":
        actor = uuid4()
    else:
        category = ReportCategory.OTHER
    with pytest.raises(ValueError, match=r"owner|precede|explanation"):
        MessageImageReport(uuid4(), actor, context, category, at)


def test_message_report_source_ids_define_causality_when_wall_clock_moves_backwards() -> None:
    store = Store()
    assert store.source is not None
    source = store.source
    issued_at = source.sent_at - timedelta(seconds=1)
    context = MessageImageReportContext(uuid4(), store.actor.session.account_id, source, issued_at)
    submitted_at = issued_at - timedelta(seconds=1)
    report = MessageImageReport(
        uuid4(), context.reporter_id, context, ReportCategory.SPAM, submitted_at
    )
    assert report.context.source is source
    assert report.context.issued_at == issued_at
    assert report.submitted_at == submitted_at
