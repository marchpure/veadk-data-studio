from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import AsyncSessionFactory
from server.schemas.agent import AgentRequest
from server.schemas.standard_response import success_response
from server.services.unified_agent import stream_handoff_agent_response
from server.utils.custom_logger import get_logger
from server.utils.streaming_utils import stream_with_keepalive

logger = get_logger(__name__)

router = APIRouter()

active_generation_tasks: dict[str, asyncio.Task] = {}


@router.post("/unified-agent/stream")
async def stream_handoff_agent(
    request: AgentRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
):
    async def stream_with_session():
        background_task = None
        event_queue = asyncio.Queue()
        completion_sentinel = object()

        try:

            async def run_generator_in_background():
                session = None
                generator = None
                notebook_id_str = str(request.notebook_id)
                try:
                    session = AsyncSessionFactory()
                    await session.__aenter__()

                    generator = stream_handoff_agent_response(
                        request, session, tenant_id=auth.tenant_id, user_id=auth.user_id
                    )
                    async for event in generator:
                        await event_queue.put(event)
                except Exception as stream_error:
                    logger.error(
                        f"Error in background generator: {stream_error}",
                        exc_info=True,
                        posthog_context={
                            "function": "stream_handoff_agent.background_generator",
                            "notebook_id": request.notebook_id,
                            "llm_connection_id": request.llm_connection_id,
                            "model": request.model,
                            "db_type": request.db_type,
                        },
                    )
                    error_event = json.dumps(
                        {"type": "error", "text": f"Stream error: {str(stream_error)}"},
                        ensure_ascii=False,
                    )
                    await event_queue.put(f"data: {error_event}\n\n")
                finally:
                    await event_queue.put(completion_sentinel)

                    if notebook_id_str in active_generation_tasks:
                        del active_generation_tasks[notebook_id_str]

                        current_task = asyncio.current_task()
                        was_cancelled = current_task and (
                            current_task.cancelled()
                            or (hasattr(current_task, "cancelling") and current_task.cancelling() > 0)
                        )

                        if was_cancelled:
                            logger.info(f"Stream generation cancelled and cleaned up for notebook {notebook_id_str}")
                        else:
                            logger.info(f"Stream generation completed and cleaned up for notebook {notebook_id_str}")

                    if session:
                        try:
                            await session.__aexit__(None, None, None)
                            logger.debug(f"Database session closed for notebook {notebook_id_str}")
                        except Exception as session_close_error:
                            logger.error(f"Error closing session in background task: {session_close_error}")

            background_task = asyncio.create_task(run_generator_in_background())

            notebook_id_str = str(request.notebook_id)
            active_generation_tasks[notebook_id_str] = background_task
            logger.info(f"Started stream generation for notebook {notebook_id_str}")

            try:
                while True:
                    event = await event_queue.get()
                    if event is completion_sentinel:
                        break
                    yield event
            except asyncio.CancelledError:
                is_task_cancelled = (
                    (
                        background_task
                        and (
                            (hasattr(background_task, "cancelling") and background_task.cancelling() > 0)
                            or background_task.cancelled()
                        )
                    )
                    if background_task
                    else False
                )
                is_task_running = (
                    background_task and not background_task.done() and not is_task_cancelled
                    if background_task
                    else False
                )

                if is_task_running:
                    logger.info(
                        f"Client disconnected for notebook {request.notebook_id}, generation continues in background"
                    )
                else:
                    logger.debug(f"Client disconnected for notebook {request.notebook_id} (generation already stopped)")

        except asyncio.CancelledError:
            is_task_cancelled = (
                (
                    background_task
                    and (
                        (hasattr(background_task, "cancelling") and background_task.cancelling() > 0)
                        or background_task.cancelled()
                    )
                )
                if background_task
                else False
            )
            is_task_running = (
                background_task and not background_task.done() and not is_task_cancelled if background_task else False
            )

            if is_task_running:
                logger.info(
                    f"Client disconnected for notebook {request.notebook_id}, generation will complete in background"
                )
            else:
                logger.debug(f"Client disconnected for notebook {request.notebook_id} (generation already stopped)")
        except Exception as streaming_error:
            logger.error(
                f"Error in streaming: {streaming_error}",
                exc_info=True,
                posthog_context={
                    "function": "stream_handoff_agent.streaming",
                    "notebook_id": request.notebook_id,
                },
            )
            error_event = json.dumps(
                {
                    "type": "error",
                    "text": f"Streaming error: {str(streaming_error)}",
                },
                ensure_ascii=False,
            )
            yield f"data: {error_event}\n\n"
        finally:
            notebook_id_str = str(request.notebook_id)

            if background_task:
                task_is_being_cancelled = (
                    hasattr(background_task, "cancelling") and background_task.cancelling() > 0
                ) or background_task.cancelled()
                task_is_running = not background_task.done() and not task_is_being_cancelled

                if task_is_running:
                    logger.info(
                        f"Stream generation still running for notebook {request.notebook_id}, allowing it to complete in background"
                    )
                elif task_is_being_cancelled:
                    logger.debug(f"Stream generation was cancelled for notebook {request.notebook_id}")
            else:
                task_is_running = False

            if background_task:
                try:
                    await asyncio.shield(asyncio.wait_for(background_task, timeout=300))
                except TimeoutError:
                    logger.warning(f"Stream generation timeout (300s) for notebook {request.notebook_id}")
                    background_task.cancel()
                except asyncio.CancelledError:
                    is_task_cancelled_now = (
                        (
                            background_task
                            and (
                                (hasattr(background_task, "cancelling") and background_task.cancelling() > 0)
                                or background_task.cancelled()
                            )
                        )
                        if background_task
                        else False
                    )
                    is_task_running_now = (
                        background_task and not background_task.done() and not is_task_cancelled_now
                        if background_task
                        else False
                    )

                    if is_task_running_now:
                        logger.info(f"Stream continues in background for notebook {request.notebook_id}")
                    else:
                        logger.debug(f"Stream wait cancelled for notebook {request.notebook_id}")
                except Exception as bg_error:
                    logger.error(f"Stream generation error for notebook {request.notebook_id}: {bg_error}")

    logger.info("Streaming handoff agent response for notebook %s", request.notebook_id)

    return StreamingResponse(
        stream_with_keepalive(stream_with_session(), keepalive_interval=15.0),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/unified-agent/abort/{notebook_id}")
async def abort_generation(
    notebook_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
):
    notebook_id_str = str(notebook_id)
    task = None
    task_key = None

    if notebook_id_str in active_generation_tasks:
        task = active_generation_tasks[notebook_id_str]
        task_key = notebook_id_str
    elif "None" in active_generation_tasks:
        logger.debug(f"Task not found under {notebook_id_str}, using 'None' key for first message abort")
        task = active_generation_tasks["None"]
        task_key = "None"

    if not task:
        logger.info(f"No active generation task found for notebook {notebook_id_str}")
        return success_response(
            data={"aborted": False, "reason": "no_active_task"},
            message="No active generation task found",
        )

    if task.done():
        logger.info(f"Generation task already completed for notebook {notebook_id_str}")
        if task_key in active_generation_tasks:
            del active_generation_tasks[task_key]
        return success_response(
            data={"aborted": False, "reason": "already_completed"},
            message="Generation already completed",
        )

    logger.info(f"Aborting stream generation for notebook {notebook_id_str}")
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info(f"Stream generation cancelled successfully for notebook {notebook_id_str}")
    except Exception as e:
        logger.error(f"Error cancelling stream generation: {e}")

    if task_key and task_key in active_generation_tasks:
        del active_generation_tasks[task_key]

    return success_response(
        data={"aborted": True},
        message="Generation aborted successfully",
    )
