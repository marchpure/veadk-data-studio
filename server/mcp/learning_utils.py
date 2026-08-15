from uuid import UUID

from server.db.session import AsyncSessionFactory
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

FILLER_WORDS = frozenset(
    {
        "can",
        "you",
        "please",
        "show",
        "me",
        "i",
        "want",
        "to",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "what",
        "how",
        "do",
        "does",
        "my",
        "of",
        "in",
        "for",
        "and",
        "or",
        "with",
        "this",
        "that",
        "it",
        "be",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "should",
        "let",
        "help",
        "tell",
        "about",
        "from",
        "on",
        "at",
        "by",
        "get",
        "give",
        "make",
        "just",
        "like",
        "also",
        "some",
        "all",
        "any",
        "hi",
        "hey",
        "hello",
        "thanks",
        "thank",
        "know",
        "need",
        "see",
        "look",
        "find",
        "think",
    }
)


def extract_search_keywords(message: str) -> str:
    words = message[:300].lower().split()
    meaningful = [w for w in words if w not in FILLER_WORDS and len(w) > 1]
    return " ".join(meaningful[:15])


async def fetch_relevant_learnings(
    tenant_id: UUID,
    message: str = "",
    dataset_ids: list[str] | None = None,
) -> list[dict] | None:
    try:
        from server.repositories.learning import LearningRepository

        async with AsyncSessionFactory() as session:
            learning_repo = LearningRepository(session)
            search_query = extract_search_keywords(message) if message else ""

            if not search_query and not dataset_ids:
                all_results = await learning_repo.list_by_tenant(limit=20)
                if all_results:
                    return [{"id": str(r.id), "title": r.title, "learning": r.learning} for r in all_results]
                return None

            all_results = []
            seen_ids: set[str] = set()

            if search_query:
                title_results = await learning_repo.search_by_title(search_query, limit=10)
                for r in title_results:
                    if str(r.id) not in seen_ids:
                        all_results.append(r)
                        seen_ids.add(str(r.id))

            if dataset_ids:
                for ds_id in dataset_ids:
                    if not ds_id:
                        continue
                    ds_results = await learning_repo.search_by_dataset_id(ds_id, limit=10)
                    for r in ds_results:
                        if str(r.id) not in seen_ids:
                            all_results.append(r)
                            seen_ids.add(str(r.id))

            if all_results:
                return [{"id": str(r.id), "title": r.title, "learning": r.learning} for r in all_results]
            return None

    except Exception as e:
        logger.warning(f"Failed to fetch learnings for MCP: {e}")
        return None
