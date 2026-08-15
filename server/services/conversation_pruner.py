"""Tier 1: Smart Pruning - Replace old tool outputs with placeholders."""

from copy import deepcopy
from datetime import datetime
from typing import Any

from server.utils.conversation_items import conversation_items_to_messages, item_to_message, normalize_content
from server.utils.custom_logger import get_logger
from server.utils.model_limits import TIER1_CONFIG
from server.utils.token_estimator import estimate_messages_tokens_fast

logger = get_logger(__name__)


class ConversationPruner:
    """
    Tier 1 context management: Aggressive tool output pruning.

    Strategy:
    - Runs after EVERY turn (lightweight)
    - Walks backwards through conversation
    - Protects last 2 user turns (recent context)
    - Replaces old tool outputs (role="tool") with placeholders
    - NEVER removes tool calls (preserves conversation structure)
    """

    def __init__(self):
        self.stats = {
            "outputs_pruned": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "tokens_saved": 0,
            "pruning_performed": False,
        }

    def prune(
        self,
        items: list[Any],
        dry_run: bool = False,
    ) -> tuple[list[Any], dict[str, Any]]:
        """
        Prune old tool outputs from conversation.

        Args:
            items: Conversation items
            dry_run: If True, only calculate stats without modifying

        Returns:
            Tuple of (pruned_items, statistics)
        """
        if not items:
            return items, self.stats

        # Convert to messages for token counting
        messages = self._items_to_messages(items)
        tokens_before = estimate_messages_tokens_fast(messages)
        self.stats["tokens_before"] = tokens_before

        # Calculate potential savings
        protected_zone_start_idx = self._find_protection_zone_start(items)

        logger.debug(
            f"[PRUNE SCAN] Total items: {len(items)}, "
            f"Protection zone starts at index: {protected_zone_start_idx}, "
            f"Items 0-{protected_zone_start_idx - 1 if protected_zone_start_idx > 0 else 0} are candidates"
        )

        # Walk backwards and identify tool outputs to prune
        prunable_indices = []
        cumulative_tokens = 0

        for idx in range(len(items) - 1, -1, -1):
            item = items[idx]
            role = self._get_role(item)

            # Skip if in protection zone
            if idx >= protected_zone_start_idx:
                continue

            # Count tokens (walking backwards)
            item_tokens = self._estimate_item_tokens(item)
            cumulative_tokens += item_tokens

            # If we're beyond the protection threshold, mark tool outputs for pruning
            if cumulative_tokens > TIER1_CONFIG["PROTECT_RECENT_TOKENS"]:
                if role == "tool":
                    content = self._get_content(item)
                    if isinstance(content, str) and len(content) > TIER1_CONFIG["MAX_TOOL_OUTPUT_LENGTH"]:
                        prunable_indices.append(idx)

        # Check if pruning is worth it - estimate actual savings
        potential_savings = 0
        for idx in prunable_indices:
            item = items[idx]
            content = self._get_content(item)
            logger.info(f"Prunable item at index {idx} with content length {len(str(content)) if content else 0} chars")
            if isinstance(content, str):
                # Estimate tokens saved (content length - placeholder length)
                placeholder_len = min(1000, len(content))
                chars_saved = len(content) - placeholder_len
                # Use character count estimate: ~4 chars per token
                logger.info("came here in this block")
                potential_savings += chars_saved // 4

        if potential_savings < TIER1_CONFIG["MIN_SAVINGS_THRESHOLD"]:
            logger.info(f"Pruning skipped: estimated savings ({potential_savings} tokens) below threshold")
            self.stats["tokens_after"] = tokens_before
            return items, self.stats

        # Perform pruning
        pruned_items = []
        for idx, item in enumerate(items):
            if idx in prunable_indices and not dry_run:
                # Log details about what's being pruned
                content = self._get_content(item)
                tool_call_id = self._get_tool_call_id(item)
                content_preview = str(content)[:100] + "..." if content and len(str(content)) > 100 else str(content)

                logger.debug(
                    f"[PRUNE] Index {idx}, tool_call_id={tool_call_id}, "
                    f"original_size={len(str(content)) if content else 0} chars, "
                    f"preview={content_preview}"
                )

                pruned_item = self._prune_tool_output(item)
                pruned_items.append(pruned_item)
                self.stats["outputs_pruned"] += 1
            else:
                pruned_items.append(item)

        # Calculate final stats
        pruned_messages = self._items_to_messages(pruned_items)
        tokens_after = estimate_messages_tokens_fast(pruned_messages)
        self.stats["tokens_after"] = tokens_after
        self.stats["tokens_saved"] = tokens_before - tokens_after
        self.stats["pruning_performed"] = not dry_run and len(prunable_indices) > 0

        logger.info(
            f"Tier 1 Pruning: {self.stats['outputs_pruned']} outputs pruned, "
            f"{self.stats['tokens_saved']} tokens saved "
            f"({tokens_before} → {tokens_after})"
        )

        return (items if dry_run else pruned_items), self.stats

    def _find_protection_zone_start(self, items: list[Any]) -> int:
        """
        Find the index where the protection zone starts.
        Protection zone = last 2 user messages + everything after.

        Returns:
            Index of the start of protection zone
        """
        user_message_indices = []
        for idx, item in enumerate(items):
            if self._get_role(item) == "user":
                user_message_indices.append(idx)

        if len(user_message_indices) < 2:
            # Protect everything if less than 2 user messages
            return 0

        # Protect from the 2nd-to-last user message onwards
        return user_message_indices[-2]

    def _prune_tool_output(self, item: Any) -> Any:
        """
        Replace tool output content with placeholder.

        Args:
            item: Tool result item (role="tool")

        Returns:
            Item with pruned content
        """
        item_copy = deepcopy(item)
        content = self._get_content(item_copy)

        if isinstance(content, str):
            original_length = len(content)
            preview_length = min(TIER1_CONFIG["MAX_TOOL_OUTPUT_LENGTH"], original_length)
            preview = content[:preview_length]

            pruned_content = (
                f"{preview}...\n\n"
                f"[Output pruned by Tier 1 context management. "
                f"Original length: {original_length:,} chars. "
                f"Timestamp: {datetime.now().isoformat()}. "
                f"Use new tool calls to retrieve data or perform acion]"
            )

            self._set_content(item_copy, pruned_content)

        return item_copy

    # ==================== Helper Methods ====================

    def _items_to_messages(self, items: list[Any]) -> list[dict[str, Any]]:
        """Convert items to message format."""
        return conversation_items_to_messages(items)

    def _estimate_item_tokens(self, item: Any) -> int:
        """Estimate tokens for a single item."""
        msg = item_to_message(item)
        if not msg:
            return 0
        return estimate_messages_tokens_fast([msg])

    def _get_role(self, item: Any) -> str:
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

    def _get_content(self, item: Any) -> Any:
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
        if isinstance(item, dict):
            item["content"] = content
            if item.get("type") == "function_call_output":
                item["output"] = content
        else:
            item.content = content
            if getattr(item, "type", None) == "function_call_output":
                item.output = content

    def _get_tool_call_id(self, item: Any) -> str | None:
        """Get tool_call_id from tool result message."""
        if isinstance(item, dict):
            return item.get("tool_call_id") or item.get("call_id") or item.get("id")
        return getattr(item, "tool_call_id", None) or getattr(item, "call_id", None) or getattr(item, "id", None)
