"""Conversation compaction service for reducing context size while preserving integrity."""

from copy import deepcopy
from typing import Any

from server.utils.conversation_items import (
    conversation_items_to_messages,
    item_to_message,
    normalize_content,
)
from server.utils.custom_logger import get_logger
from server.utils.token_utils import count_conversation_tokens

logger = get_logger(__name__)

# Informative placeholders for removed tool calls - guides model to re-call if needed
TOOL_PLACEHOLDERS = {
    "execute_sql_query": "[SQL query executed previously. Use execute_sql_query again if you need fresh results]",
    "execute_mongo_query": "[MongoDB query executed previously. Use execute_mongo_query again if you need fresh results]",
    "execute_duckdb_query": "[DuckDB query executed previously. Use execute_duckdb_query again if you need fresh results]",
    "save_query": "[Query saved successfully. Use saved_query_schema to see all saved queries]",
    "get_existing_html": "[HTML fetched previously. Use get_existing_html for current dashboard state]",
    "dashboard_search_replace": "[HTML edit applied. Use get_existing_html to see current dashboard]",
    "apply_html_patch": "[HTML patch applied. Use get_existing_html to see current dashboard]",
    "start_html_generation": "[HTML generation started. Proceed with editing tools]",
    "get_chart_styling": "[Chart styling guidelines fetched. Call get_chart_styling again if needed]",
    "get_user_style_guidelines": "[Style guidelines fetched. Call get_user_style_guidelines again if needed]",
    "search_instructions": "[Instructions searched. Use search_instructions again if needed]",
}

# Tools to NEVER compact (keep full content)
ESSENTIAL_TOOLS = {
    "get_database_schema",  # Critical for data understanding
    "saved_query_schema",  # Keep only the LATEST one (handled specially)
    "get_skill_definition",  # Keep loaded skill docs for API calls
    "search_enabled_skills",  # Preserve skill search results
    "execute_skill_api",  # Preserve skill API responses
}


class ConversationCompactor:
    """
    Compacts conversation history while preserving:
    - All user messages
    - All assistant responses
    - Tool call integrity (id references must not break)
    - Essential tools (get_database_schema, latest saved_query_schema)

    All other tool calls are replaced with informative placeholders that
    guide the model to re-call if needed.
    """

    # Tools that execute queries (replace with placeholder)
    QUERY_EXECUTION_TOOLS = {
        "execute_sql_query",
        "execute_mongo_query",
        "execute_duckdb_query",
    }

    # Schema inspection tools (keep only latest)
    SCHEMA_TOOLS = {"saved_query_schema"}

    # Query save tools (replace with placeholder)
    SAVE_TOOLS = {"save_query"}

    # HTML tools (replace with placeholder)
    HTML_TOOLS = {
        "get_existing_html",
        "dashboard_search_replace",
        "apply_html_patch",
        "start_html_generation",
    }

    # Guideline tools (replace with placeholder)
    GUIDELINE_TOOLS = {
        "get_chart_styling",
        "get_user_style_guidelines",
        "search_instructions",
    }

    SKILL_TOOLS: set[str] = set()

    # Maximum characters to keep in redacted results
    MAX_RESULT_PREVIEW_CHARS = 500

    def __init__(self):
        self.stats = {
            "items_removed": 0,
            "items_redacted": 0,
            "tool_calls_removed": 0,
            "tool_results_removed": 0,
            "tokens_before": 0,
            "tokens_after": 0,
        }

    def compact(
        self, items: list[Any], model: str = "gpt-4", dry_run: bool = False
    ) -> tuple[list[Any], dict[str, Any]]:
        """
        Compact conversation items.

        Args:
            items: List of conversation items (dicts or objects)
            model: Model name for token counting
            dry_run: If True, only calculate stats without modifying

        Returns:
            Tuple of (compacted_items, statistics)
        """
        if not items:
            return items, self.stats

        # Count tokens before compaction
        messages = self._items_to_messages(items)
        token_stats = count_conversation_tokens(messages, model)
        self.stats["tokens_before"] = token_stats["total_tokens"]

        # Phase 1: Analyze conversation structure
        tool_call_analysis = self._analyze_tool_calls(items)

        # Phase 2: Identify which tool calls to keep
        keep_tool_call_ids = self._identify_keeper_tool_calls(tool_call_analysis)

        # Phase 3: Build compacted conversation
        compacted = []

        for idx, item in enumerate(items):
            role = self._get_role(item)

            # Always keep user messages
            if role == "user":
                compacted.append(item)
                continue

            # Always keep assistant text responses (without tool calls)
            if role == "assistant" and not self._has_tool_calls(item):
                compacted.append(item)
                continue

            # Handle assistant messages with tool calls
            if role == "assistant" and self._has_tool_calls(item):
                compacted_item = self._compact_tool_call_message(item, keep_tool_call_ids)
                if compacted_item:
                    compacted.append(compacted_item)
                continue

            # Handle tool results (role="tool")
            if role == "tool":
                tool_call_id = self._get_tool_call_id_from_result(item)
                if tool_call_id and tool_call_id in keep_tool_call_ids:
                    # Keep essential tools with redacted large results
                    compacted_item = self._redact_large_tool_result(item)
                    compacted.append(compacted_item)
                else:
                    # Replace with placeholder instead of removing
                    tool_name = tool_call_analysis.get("tool_id_to_name", {}).get(tool_call_id)
                    compacted_item = self._replace_with_placeholder(item, tool_name)
                    compacted.append(compacted_item)
                    self.stats["tool_results_removed"] += 1
                continue

            # Default: keep unknown message types
            compacted.append(item)

        # Count tokens after compaction
        messages_after = self._items_to_messages(compacted)
        token_stats_after = count_conversation_tokens(messages_after, model)
        self.stats["tokens_after"] = token_stats_after["total_tokens"]
        self.stats["tokens_saved"] = self.stats["tokens_before"] - self.stats["tokens_after"]
        self.stats["reduction_percentage"] = (
            round((self.stats["tokens_saved"] / self.stats["tokens_before"] * 100), 2)
            if self.stats["tokens_before"] > 0
            else 0
        )

        return (items if dry_run else compacted), self.stats

    def _analyze_tool_calls(self, items: list[Any]) -> dict[str, Any]:
        """
        Analyze all tool calls in the conversation.

        Returns dict with:
            - all_tool_calls: list of (index, tool_call_id, tool_name)
            - schema_calls: list of saved_query_schema call IDs
            - save_calls: list of save_query call IDs
            - execution_calls: list of execute_* call IDs
            - html_calls: list of HTML tool call IDs
            - guideline_calls: list of guideline tool call IDs
            - essential_calls: list of essential tool call IDs (always keep)
            - tool_id_to_name: mapping of tool_call_id to tool_name
        """
        analysis = {
            "all_tool_calls": [],
            "schema_calls": [],
            "save_calls": [],
            "execution_calls": [],
            "html_calls": [],
            "guideline_calls": [],
            "skill_calls": [],
            "essential_calls": [],
            "tool_id_to_name": {},  # For placeholder lookup
        }

        for idx, item in enumerate(items):
            tool_calls = self._get_tool_calls(item)
            for tc in tool_calls:
                tool_name = self._get_tool_name(tc)
                tool_call_id = self._get_tool_call_id_from_call(tc)

                if not tool_call_id or not tool_name:
                    continue

                analysis["all_tool_calls"].append((idx, tool_call_id, tool_name))
                analysis["tool_id_to_name"][tool_call_id] = tool_name

                if tool_name in ESSENTIAL_TOOLS and tool_name != "saved_query_schema":
                    # get_database_schema is always essential
                    analysis["essential_calls"].append(tool_call_id)
                elif tool_name in self.SCHEMA_TOOLS:
                    analysis["schema_calls"].append(tool_call_id)
                elif tool_name in self.SAVE_TOOLS:
                    analysis["save_calls"].append(tool_call_id)
                elif tool_name in self.QUERY_EXECUTION_TOOLS:
                    analysis["execution_calls"].append(tool_call_id)
                elif tool_name in self.HTML_TOOLS:
                    analysis["html_calls"].append(tool_call_id)
                elif tool_name in self.GUIDELINE_TOOLS:
                    analysis["guideline_calls"].append(tool_call_id)
                elif tool_name in self.SKILL_TOOLS:
                    analysis["skill_calls"].append(tool_call_id)

        return analysis

    def _identify_keeper_tool_calls(self, analysis: dict[str, Any]) -> set[str]:
        """
        Identify which tool call IDs must be kept (with full content).

        Aggressive Strategy:
        1. Keep only essential tools (get_database_schema)
        2. Keep ONLY the most recent saved_query_schema
        3. ALL other tool calls get replaced with placeholders
        """
        keepers: set[str] = set()

        # Keep essential tools (get_database_schema)
        keepers.update(analysis.get("essential_calls", []))

        # Keep only the most recent saved_query_schema
        if analysis["schema_calls"]:
            # The last one in the list is the most recent
            most_recent_schema = analysis["schema_calls"][-1]
            keepers.add(most_recent_schema)
            removed_schema_count = len(analysis["schema_calls"]) - 1
            if removed_schema_count > 0:
                logger.info(f"Compacting {removed_schema_count} old saved_query_schema calls to placeholders")

        # Log what's being compacted
        compacted_count = (
            len(analysis["save_calls"])
            + len(analysis["execution_calls"])
            + len(analysis.get("html_calls", []))
            + len(analysis.get("guideline_calls", []))
            + len(analysis.get("skill_calls", []))
        )
        if compacted_count > 0:
            logger.info(
                f"Compacting {compacted_count} tool calls to placeholders "
                f"(save: {len(analysis['save_calls'])}, exec: {len(analysis['execution_calls'])}, "
                f"html: {len(analysis.get('html_calls', []))}, guidelines: {len(analysis.get('guideline_calls', []))}, "
                f"skills: {len(analysis.get('skill_calls', []))})"
            )

        return keepers

    def _compact_tool_call_message(self, item: Any, keep_tool_call_ids: set[str]) -> Any | None:
        """
        Keep assistant messages with tool calls for structure integrity.

        We keep all tool calls so that the corresponding tool results
        (now as placeholders) have valid references.
        """
        tool_calls = self._get_tool_calls(item)

        # Count how many would be removed (for stats)
        for tc in tool_calls:
            tool_call_id = self._get_tool_call_id_from_call(tc)
            if tool_call_id and tool_call_id not in keep_tool_call_ids:
                self.stats["tool_calls_removed"] += 1

        # Keep all tool calls for structure integrity
        # The corresponding tool results will be replaced with placeholders
        return item

    def _redact_large_tool_result(self, item: Any) -> Any:
        """
        Redact large tool result content while keeping structure.

        For results with large content, truncate to preview size.
        """
        item_copy = deepcopy(item)
        content = self._get_content(item_copy)

        if isinstance(content, str) and len(content) > self.MAX_RESULT_PREVIEW_CHARS:
            preview = content[: self.MAX_RESULT_PREVIEW_CHARS]
            redacted = f"{preview}... [result truncated for context efficiency, original length: {len(content)} chars]"
            self._set_content(item_copy, redacted)
            self.stats["items_redacted"] += 1

        return item_copy

    def _replace_with_placeholder(self, item: Any, tool_name: str | None) -> Any:
        """
        Replace tool result content with an informative placeholder.

        The placeholder guides the model to re-call the tool if needed.
        """
        item_copy = deepcopy(item)

        # Get appropriate placeholder for this tool
        if tool_name and tool_name in TOOL_PLACEHOLDERS:
            placeholder = TOOL_PLACEHOLDERS[tool_name]
        else:
            # Generic placeholder for unknown tools
            placeholder = (
                f"[Tool '{tool_name or 'unknown'}' was called previously. Call again if you need fresh results]"
            )

        self._set_content(item_copy, placeholder)
        self.stats["items_redacted"] += 1

        return item_copy

    # ==================== Helper Methods ====================

    def _items_to_messages(self, items: list[Any]) -> list[dict[str, Any]]:
        """Convert items to OpenAI message format for token counting."""
        return conversation_items_to_messages(items)

    def _get_role(self, item: Any) -> str:
        """Extract role from item (dict or object)."""
        if isinstance(item, dict):
            if item.get("type") == "function_call_output":
                return "tool"
            if item.get("type") == "function_call":
                return "assistant"
            return item.get("role", "unknown")

        item_type = getattr(item, "type", None)
        if item_type == "function_call_output":
            return "tool"
        if item_type == "function_call":
            return "assistant"
        return getattr(item, "role", "unknown")

    def _has_tool_calls(self, item: Any) -> bool:
        """Check if item has tool calls."""
        tool_calls = self._get_tool_calls(item)
        return bool(tool_calls)

    def _get_tool_calls(self, item: Any) -> list[Any]:
        """Get tool calls from item."""
        msg = item_to_message(item)
        if msg and msg.get("tool_calls"):
            return msg.get("tool_calls", [])
        return []

    def _set_tool_calls(self, item: Any, tool_calls: list[Any]) -> None:
        """Set tool calls on item."""
        if isinstance(item, dict):
            item["tool_calls"] = tool_calls
        else:
            item.tool_calls = tool_calls

    def _get_tool_name(self, tool_call: Any) -> str | None:
        """Extract tool name from tool call."""
        if isinstance(tool_call, dict):
            function_data = tool_call.get("function") or {}
            return function_data.get("name")
        # Object-based tool call
        if hasattr(tool_call, "function") and hasattr(tool_call.function, "name"):
            return tool_call.function.name
        return None

    def _get_tool_call_id_from_call(self, tool_call: Any) -> str | None:
        """Extract tool call ID from a tool call."""
        if isinstance(tool_call, dict):
            return tool_call.get("id") or tool_call.get("call_id")
        return getattr(tool_call, "id", None) or getattr(tool_call, "call_id", None)

    def _get_tool_call_id_from_result(self, item: Any) -> str | None:
        """Extract tool_call_id from a tool result message."""
        if isinstance(item, dict):
            return item.get("tool_call_id") or item.get("call_id") or item.get("id")
        return getattr(item, "tool_call_id", None) or getattr(item, "call_id", None) or getattr(item, "id", None)

    def _get_content(self, item: Any) -> Any:
        """Get content from item."""
        if isinstance(item, dict):
            raw_content = item.get("content")
            if raw_content is None and item.get("type") == "function_call_output":
                raw_content = item.get("output")
            return normalize_content(raw_content)

        raw_content = getattr(item, "content", None)
        if raw_content is None and getattr(item, "type", None) == "function_call_output":
            raw_content = getattr(item, "output", None)
        return normalize_content(raw_content)

    def _set_content(self, item: Any, content: Any) -> None:
        """Set content on item."""
        if isinstance(item, dict):
            item["content"] = content
            if item.get("type") == "function_call_output":
                item["output"] = content
        else:
            item.content = content
            if getattr(item, "type", None) == "function_call_output":
                item.output = content
