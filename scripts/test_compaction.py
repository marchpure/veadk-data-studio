"""Debug helper to inspect token estimates for a notebook conversation.

Run with:

    python scripts/test_compaction.py --notebook-id <NOTEBOOK_ID> [--model gpt-4]

This prints fast/exact token counts, a per-message breakdown, and a compaction
dry-run summary so you can debug context usage for a specific notebook.
"""

from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when running as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sqlalchemy.engine import make_url

from server.db.session import DATABASE_URL
from server.services.conversation_compactor import ConversationCompactor
from server.services.conversation_state import ConversationStateSession
from server.utils.conversation_items import item_to_message, normalize_content
from server.utils.token_estimator import estimate_messages_tokens_fast
from server.utils.token_utils import count_conversation_tokens


def _get_agent_session_db_path() -> str:
    """Local copy of the helper to derive the agent session SQLite path."""

    try:
        url = make_url(DATABASE_URL)
        if url.drivername.startswith("sqlite"):
            db_path = url.database

            if not db_path or db_path == ":memory:":
                return ":memory:"

            db_file = Path(db_path)
            parent_dir = db_file.parent
            return str(parent_dir / "agent_sessions.db")
    except Exception:
        pass

    return str(ROOT / ".data" / "agent_sessions.db")


def _preview_text(content: str, limit: int = 120) -> str:
    snippet = content.replace("\n", " ")
    return snippet[:limit] + ("…" if len(snippet) > limit else "")


def _describe_item_type(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("type") or item.get("role") or "unknown"
    return getattr(item, "type", None) or getattr(item, "role", "unknown")


async def run(notebook_id: str, model: str, skip_compactor: bool) -> None:
    session_path = _get_agent_session_db_path()
    session = ConversationStateSession(notebook_id, session_path)

    items = await session.get_items()
    if not items:
        print(f"No conversation items found for notebook {notebook_id}")
        return

    normalized_pairs: list[tuple[Any, dict[str, Any]]] = []
    for raw_item in items:
        msg = item_to_message(raw_item)
        if msg:
            normalized_pairs.append((raw_item, msg))

    messages = [msg for _, msg in normalized_pairs]

    fast_tokens = estimate_messages_tokens_fast(messages)
    exact_stats = count_conversation_tokens(messages, model)

    print(f"Notebook: {notebook_id}")
    print(f"Session path: {session_path}")
    print(f"Raw items: {len(items)} | Normalized messages: {len(messages)}")
    print(f"Fast token estimate: {fast_tokens}")
    print(
        "Exact token count: {total} (by role: {by_role})".format(
            total=exact_stats.get("total_tokens", 0),
            by_role=exact_stats.get("by_role", {}),
        )
    )

    print("\nPer-message estimates:")
    for idx, (raw_item, msg) in enumerate(normalized_pairs):
        tokens = estimate_messages_tokens_fast([msg])
        role = msg.get("role", "unknown")
        item_type = _describe_item_type(raw_item)
        tool_calls = msg.get("tool_calls") or []
        tool_call_id = msg.get("tool_call_id")
        preview = _preview_text(normalize_content(msg.get("content", "")))

        line = (
            f"[{idx:03d}] role={role:<9} type={item_type:<24} "
            f"tcalls={len(tool_calls):<2} tool_call_id={tool_call_id or '-':<24} "
            f"tokens~{tokens:<6} preview={preview}"
        )
        print(line)

    if skip_compactor:
        return

    compactor = ConversationCompactor()
    compacted, stats = compactor.compact(items, model=model, dry_run=True)
    print("\nCompactor dry-run stats:")
    for key in [
        "tokens_before",
        "tokens_after",
        "tokens_saved",
        "reduction_percentage",
        "items_removed",
        "items_redacted",
        "tool_calls_removed",
        "tool_results_removed",
    ]:
        if key in stats:
            print(f"  {key}: {stats.get(key)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect token usage for a notebook conversation.")
    parser.add_argument("--notebook-id", required=True, help="Notebook/session identifier")
    parser.add_argument("--model", default="gpt-4", help="Model name for exact token counting")
    parser.add_argument(
        "--skip-compactor",
        action="store_true",
        help="Skip running the compactor dry-run stats",
    )

    args = parser.parse_args()

    asyncio.run(run(args.notebook_id, args.model, args.skip_compactor))


if __name__ == "__main__":
    main()
