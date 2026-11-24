"""Defer only this task's publication SELECT spans until empty work is proven."""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

MAX_DEFERRED_QUERIES = 16


class PublicationQueries:
    def __init__(self) -> None:
        self.task_id = id(asyncio.current_task())
        self.pending = 0
        self.keep = False
        self.closed = False
        self.empty = False
        self.completed: list[Callable[[], None]] = []

    def retain(self) -> None:
        self.keep = True
        callbacks, self.completed = self.completed, []
        for callback in callbacks:
            callback()

    def finish(self, export: Callable[[], None], outcome: str) -> None:
        self.pending -= 1
        if outcome != "success" or len(self.completed) >= MAX_DEFERRED_QUERIES:
            self.retain()
        if self.keep or self.closed:
            export()
        else:
            self.completed.append(export)

    def close(self) -> None:
        self.closed = True
        if not self.empty or self.pending or self.keep:
            self.retain()
        else:
            # These callbacks have never created spans. Only proven empty SELECT
            # polls reach here; no sampler, processor or exporter discards traces.
            self.completed.clear()


_PUBLICATION: ContextVar[PublicationQueries | None] = ContextVar(
    "change_publication_queries", default=None
)


def publication_queries() -> PublicationQueries | None:
    scope = _PUBLICATION.get()
    if scope is None or scope.closed or scope.task_id != id(asyncio.current_task()):
        return None
    return scope


@contextmanager
def defer_empty_publication() -> Iterator[PublicationQueries]:
    scope = PublicationQueries()
    token = _PUBLICATION.set(scope)
    try:
        yield scope
    except BaseException:
        scope.retain()
        raise
    finally:
        try:
            scope.close()
        finally:
            _PUBLICATION.reset(token)
