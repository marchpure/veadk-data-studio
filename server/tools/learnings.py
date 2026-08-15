import json
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper

from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.repositories.learning import LearningRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


@function_tool
async def add_learning(
    ctx: RunContextWrapper[Any],
    title: str,
    learning: str,
    dataset_id: str = "",
) -> str:
    """
    Save a NEW learning to the workspace knowledge base.
    IMPORTANT: Before calling this, you MUST call search_learnings first to check if a learning
    about the SAME TOPIC already exists. If it does, use update_learning instead.
    Multiple learnings per datasource are fine — each should capture a different insight.
    Only create a new learning if the topic is genuinely different from existing ones.

    Title should reference the datasource name AND the specific insight.
    Good: "orders table — amount column is in cents, divide by 100"
    Good: "orders table — JOIN on fiscal_year not calendar_year"
    Bad: "Q1 sales results" or "New York revenue" (query results, not insights)
    Bad: any learning that contains a SQL query, MongoDB query, or code snippet

    Args:
        ctx: Run context wrapper
        title: Datasource-level category title (max 500 chars) — this is the primary search key
        learning: The lesson as a plain fact, rule, or correction — no code, no SQL, no query text
        dataset_id: Optional UUID of the dataset this learning belongs to (from get_database_schema or get_dataset_schema_by_id)

    Returns:
        JSON confirmation with the learning ID.
    """
    tenant_id = ctx.context.get("tenant_id")
    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    title = title.strip()
    learning = learning.strip()
    if not title:
        return json.dumps({"success": False, "error": "Title cannot be empty"})
    if not learning:
        return json.dumps({"success": False, "error": "Learning cannot be empty"})

    try:
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = LearningRepository(session)
            create_data: dict = {"title": title, "learning": learning}
            if dataset_id and dataset_id.strip():
                create_data["dataset_id"] = dataset_id.strip()
            new_learning = await repo.create(create_data)
            logger.info(f"[LEARNING] Added: '{title}' (dataset_id={dataset_id or 'none'})")
            return json.dumps(
                {
                    "success": True,
                    "learning_id": str(new_learning.id),
                    "message": f"Saved new learning: {title}",
                }
            )

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error adding learning: {e}")
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def update_learning(
    ctx: RunContextWrapper[Any],
    learning_id: str,
    learning: str,
    title: str = "",
    dataset_id: str = "",
) -> str:
    """
    Update an existing learning by ID. Use this to compound new insights into an existing learning
    or to refine its title.

    Typical flow: search_learnings → get_learning → merge content → update_learning with combined text.

    Args:
        ctx: Run context wrapper
        learning_id: UUID of the learning to update (from search_learnings or get_learning)
        learning: The updated content (replaces existing content entirely)
        title: New title (optional — only provide if refining the category key)
        dataset_id: Optional UUID of the dataset to link (use when learning wasn't linked before)

    Returns:
        JSON confirmation with the learning ID.
    """
    tenant_id = ctx.context.get("tenant_id")
    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    learning = learning.strip()
    if not learning:
        return json.dumps({"success": False, "error": "Learning content cannot be empty"})

    try:
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = LearningRepository(session)

            existing = await repo.get(learning_id.strip())
            if not existing:
                return json.dumps({"success": False, "error": f"Learning {learning_id} not found"})

            update_data: dict = {"learning": learning}
            if title and title.strip():
                update_data["title"] = title.strip()
            if dataset_id and dataset_id.strip():
                update_data["dataset_id"] = dataset_id.strip()

            updated = await repo.update(existing.id, update_data)
            logger.info(f"[LEARNING] Updated: '{updated.title}'")
            return json.dumps(
                {
                    "success": True,
                    "learning_id": str(updated.id),
                    "message": f"Updated learning: {updated.title}",
                }
            )

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error updating learning: {e}")
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def search_learnings(
    ctx: RunContextWrapper[Any],
    query: str,
    dataset_id: str = "",
) -> str:
    """
    Search the workspace knowledge base for previously discovered insights.
    Call this EARLY — before writing queries, exploring repos, or using skills — to check if
    a past conversation already figured out where data lives, what went wrong, or how something works.

    Use broad keywords from the user's question. If the first search misses, try synonyms or
    related terms (e.g. "fuel" if "oil" returned nothing, "auth" if "login" returned nothing).

    When both query and dataset_id are provided, returns learnings matching either (OR logic).

    Args:
        ctx: Run context wrapper
        query: Keywords to search (e.g. "oil prices", "customer churn", "auth flow").
               Use the core nouns/topics from the user's question — broad terms work best.
        dataset_id: Optional UUID of a dataset to find learnings linked to it

    Returns:
        JSON array of matching learnings with id, title, and content, ordered by most recently updated.
    """
    tenant_id = ctx.context.get("tenant_id")
    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    query = query.strip() if query else ""
    dataset_id = dataset_id.strip() if dataset_id else ""

    if not query and not dataset_id:
        return json.dumps({"success": False, "error": "Query or dataset_id required"})

    try:
        logger.info(f"[LEARNING] Search query: '{query}', dataset_id: '{dataset_id}'")
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = LearningRepository(session)
            results = await repo.search_by_title(query, dataset_id=dataset_id, limit=50)

            if results:
                titles = [r.title for r in results]
                logger.info(f"[LEARNING] Found {len(results)} match(es): {titles}")
            else:
                logger.info("[LEARNING] No matches found")

            return json.dumps(
                {
                    "success": True,
                    "results": [{"id": str(r.id), "title": r.title} for r in results],
                    "count": len(results),
                }
            )

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error searching learnings: {e}")
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def get_learning(
    ctx: RunContextWrapper[Any],
    learning_id: str,
) -> str:
    """
    Fetch the full content of a learning by its ID.
    Use this after search_learnings to read the complete learning content.

    Args:
        ctx: Run context wrapper
        learning_id: UUID of the learning (from search_learnings results)

    Returns:
        JSON with id, title, learning content, and timestamps.
    """
    tenant_id = ctx.context.get("tenant_id")
    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    if not learning_id or not learning_id.strip():
        return json.dumps({"success": False, "error": "learning_id cannot be empty"})

    try:
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = LearningRepository(session)
            result = await repo.get(learning_id.strip())

            if not result:
                return json.dumps({"success": False, "error": f"Learning {learning_id} not found"})

            return json.dumps(
                {
                    "success": True,
                    "id": str(result.id),
                    "title": result.title,
                    "learning": result.learning,
                    "dataset_id": str(result.dataset_id) if result.dataset_id else None,
                    "created_at": result.created_at.isoformat() if result.created_at else None,
                    "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                }
            )

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error getting learning: {e}")
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def remove_learning(
    ctx: RunContextWrapper[Any],
    learning_id: str,
) -> str:
    """
    Remove a learning from the workspace knowledge base by its ID.

    Args:
        ctx: Run context wrapper
        learning_id: The UUID of the learning to remove

    Returns:
        JSON confirmation of deletion.
    """
    tenant_id = ctx.context.get("tenant_id")
    if not tenant_id:
        return json.dumps({"success": False, "error": "No tenant_id in context"})

    if not learning_id or not learning_id.strip():
        return json.dumps({"success": False, "error": "learning_id cannot be empty"})

    try:
        async for session in get_async_session():
            set_tenant_id(tenant_id)
            repo = LearningRepository(session)
            deleted = await repo.delete(learning_id.strip())
            if deleted:
                logger.info(f"[LEARNING] Removed: {learning_id}")
                return json.dumps({"success": True, "message": f"Learning {learning_id} removed"})
            else:
                return json.dumps({"success": False, "error": f"Learning {learning_id} not found"})

        return json.dumps({"success": False, "error": "Failed to obtain database session"})
    except Exception as e:
        logger.error(f"Error removing learning: {e}")
        return json.dumps({"success": False, "error": str(e)})


def get_learning_tools():
    return [add_learning, update_learning, search_learnings, get_learning, remove_learning]
