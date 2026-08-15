from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


async def stream_with_keepalive(
    stream: AsyncGenerator[str, None],
    keepalive_interval: float = 15.0,
    keepalive_event: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    if keepalive_event is None:
        keepalive_event = {"type": "keepalive"}

    keepalive_data = json.dumps(keepalive_event, ensure_ascii=False)
    keepalive_chunk = f"data: {keepalive_data}\n\n"

    next_chunk_task = None
    stream_iter = stream.__aiter__()

    try:
        while True:
            try:
                if next_chunk_task is None:
                    next_chunk_task = asyncio.create_task(stream_iter.__anext__())

                done, _ = await asyncio.wait(
                    [next_chunk_task], timeout=keepalive_interval, return_when=asyncio.FIRST_COMPLETED
                )

                if done:
                    chunk = await next_chunk_task
                    next_chunk_task = None
                    yield chunk
                else:
                    logger.debug(f"Sending keepalive (no events for {keepalive_interval}s)")
                    yield keepalive_chunk

            except StopAsyncIteration:
                logger.debug("Stream completed")
                break
            except Exception as e:
                logger.error(
                    f"Error in stream_with_keepalive: {e}",
                    posthog_context={"function": "stream_with_keepalive", "keepalive_interval": keepalive_interval},
                )
                raise
    finally:
        if next_chunk_task and not next_chunk_task.done():
            next_chunk_task.cancel()
            try:
                await next_chunk_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        await stream.aclose()
        logger.debug("Source stream closed")
