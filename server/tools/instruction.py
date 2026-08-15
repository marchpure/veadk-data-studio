import json
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.settings import SettingRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

INSTRUCTIONS_WORD_LIMIT = 2000
WORKSPACE_INSTRUCTIONS_KEY = "workspace_instructions"


def _count_words(text: str) -> int:
    return len(text.split())


async def _read_existing_instructions(tenant_id: str) -> str | None:
    async for session in get_async_session():
        set_tenant_id(tenant_id)
        repo = SettingRepository(session)
        setting = await repo.get_by_key(WORKSPACE_INSTRUCTIONS_KEY)
        return setting.setting_value if setting and setting.setting_value else None
    return None


async def _save_instructions(tenant_id: str, content: str) -> None:
    async for session in get_async_session():
        set_tenant_id(tenant_id)
        repo = SettingRepository(session)
        await repo.upsert_setting(WORKSPACE_INSTRUCTIONS_KEY, content)


@function_tool
async def search_instructions(
    ctx: RunContextWrapper[Any],
    query: str,
) -> str:
    """
    Search workspace instructions for sections matching a keyword query.
    Use this in long conversations where context may have been compacted and you need
    to retrieve specific preferences or instructions you previously saved.

    Returns trimmed context snippets around each match, not the full content.

    Args:
        ctx: Run context wrapper
        query: Space-separated keywords to search for in the instructions

    Returns:
        JSON with matching snippets from the workspace instructions.
    """
    tenant_id = ctx.context.get("tenant_id")

    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    if not query or not query.strip():
        return json.dumps({"success": False, "error": "Query cannot be empty"})

    try:
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = SettingRepository(session)
            result = await repo.search_by_key_content(WORKSPACE_INSTRUCTIONS_KEY, query)

            if result is None:
                return json.dumps(
                    {"success": True, "snippets": [], "match_count": 0, "message": "No matching instructions found"}
                )

            return json.dumps(
                {
                    "success": True,
                    "snippets": result["snippets"],
                    "match_count": len(result["snippets"]),
                    "content_length": result["content_length"],
                }
            )

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error searching instructions: {e}")
        return json.dumps({"success": False, "error": str(e)})


def get_instruction_tools():
    return [search_instructions]
