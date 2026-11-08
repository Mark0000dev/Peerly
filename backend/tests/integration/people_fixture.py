from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.discovery.photos import ReadDiscoveryPhoto
from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.identity.sessions import SessionCredential
from studymate.application.safety.block_list import ReadOwnBlocks
from studymate.application.safety.blocks import ChangeOwnBlock
from studymate.application.safety.message_reports import (
    IssueMessageImageReportContext,
    SubmitMessageImageReport,
)
from studymate.application.safety.profile_reports import SubmitProfileReport
from studymate.infrastructure.persistence.block_list import SqlOwnBlocksUnitOfWork
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.product_events import record_message_report_event
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportUnitOfWork
from studymate.infrastructure.safety.message_reports import SqlMessageReportUnitOfWork
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.people import PeopleServices
from tests.integration.http_identity import ORIGIN, BrowserHarness, verified
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.registration_fixture import documents
from tests.integration.student_actor import Actor, actor


@dataclass(frozen=True, slots=True)
class PeopleHarness:
    viewer: Actor
    peer: Actor
    services: PeopleServices


async def mounted(browser: BrowserHarness, engine: AsyncEngine) -> PeopleHarness:
    await verified(browser, engine)
    cookie = browser.client.cookies.get(SESSION_COOKIE)
    assert cookie is not None
    viewer = await ready_setup(engine, SessionCredential(cookie))
    await documents(engine)
    await complete_existing_setup(engine, viewer)
    peer = await actor(engine)
    await ready_setup(engine, peer.credential)
    await complete_existing_setup(engine, peer)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprinter = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    profiles = SqlDiscoveryProfileUnitOfWork(sessions)
    services = PeopleServices(
        ReadDiscoveryProfile(profiles, hasher),
        ReadDiscoveryPhoto(profiles, hasher, browser.storage),
        SubmitProfileReport(SqlProfileReportUnitOfWork(sessions), hasher, fingerprinter),
        SubmitMessageImageReport(
            SqlMessageReportUnitOfWork(sessions, record_message_report_event), hasher, fingerprinter
        ),
        IssueMessageImageReportContext(
            SqlMessageReportUnitOfWork(sessions, record_message_report_event), hasher
        ),
        ChangeOwnBlock(SqlBlockUnitOfWork(sessions), hasher, fingerprinter),
        ReadOwnBlocks(SqlOwnBlocksUnitOfWork(sessions), hasher),
        HmacBrowserTokenSigner(bytes.fromhex("02" * 32)),
        BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
    )
    return PeopleHarness(viewer, peer, services)
