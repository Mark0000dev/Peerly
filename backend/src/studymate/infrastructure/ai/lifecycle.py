import asyncio
from contextlib import suppress


async def settle_cleanup[T](task: asyncio.Task[T]) -> T:
    """Finish already-started process/file cleanup despite repeated caller cancellation.

    Only call from a cancellation handler which re-raises cancellation afterward.
    Never use this to ignore a cancelled product operation.
    """
    while not task.done():
        with suppress(asyncio.CancelledError):
            await asyncio.shield(task)
    return task.result()
