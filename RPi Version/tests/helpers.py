from __future__ import annotations

import asyncio
from collections.abc import Callable


async def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    """Attend une condition asyncio sans imposer un délai fixe aux tests."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition non satisfaite avant le délai")
        await asyncio.sleep(0.001)
