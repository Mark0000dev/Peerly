import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.catalogue import CatalogueQuery, SearchSubjects
from studymate.application.identity.sessions import StudentActionDeniedError
from studymate.infrastructure.persistence.catalogue_search import SqlCatalogueUnitOfWork
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


def service(engine: AsyncEngine) -> SearchSubjects:
    return SearchSubjects(
        SqlCatalogueUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        Sha256SessionHasher(),
    )


async def test_catalogue_empty_and_unverified_access_are_honest(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    search = service(identity_engine)
    empty = await search(owner.credential, CatalogueQuery())
    assert empty.items == ()
    assert empty.next_cursor is None
    unverified = await actor(identity_engine, verified=False)
    with pytest.raises(StudentActionDeniedError):
        await search(unverified.credential, CatalogueQuery())


async def test_catalogue_name_alias_search_and_literal_wildcards(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    search = service(identity_engine)
    first = await subject(
        identity_engine, name="Synthetic Straße", aliases=("First alias", "Second alias")
    )
    second = await subject(identity_engine, name="Synthetic 100%", aliases=("Literal_underscore",))
    await subject(identity_engine, name="Archived synthetic", archived=True)
    page = await search(owner.credential, CatalogueQuery("  STRASSE  "))
    assert page.items == (first,)
    alias = await search(owner.credential, CatalogueQuery("ALIAS"))
    assert alias.items == (first,)
    assert (await search(owner.credential, CatalogueQuery("%"))).items == (second,)
    assert (await search(owner.credential, CatalogueQuery("_"))).items == (second,)
    assert (await search(owner.credential, CatalogueQuery("archived"))).items == ()
    assert (await search(owner.credential, CatalogueQuery("' OR true; --"))).items == ()


async def test_catalogue_cursor_has_no_overlap_and_is_bound_to_query(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    search = service(identity_engine)
    last = await subject(identity_engine, name="Synthetic Z", aliases=())
    first = await subject(identity_engine, name="Synthetic A", aliases=())
    middle = await subject(identity_engine, name="Synthetic M", aliases=())
    page = await search(owner.credential, CatalogueQuery(limit=1))
    assert page.items == (first,)
    assert page.next_cursor is not None
    second = await search(owner.credential, CatalogueQuery(limit=1, cursor=page.next_cursor))
    assert second.items == (middle,)
    assert second.next_cursor is not None
    third = await search(owner.credential, CatalogueQuery(limit=1, cursor=second.next_cursor))
    assert third.items == (last,)
    assert third.next_cursor is None
    with pytest.raises(ValueError, match="different search"):
        CatalogueQuery("changed", cursor=page.next_cursor)
