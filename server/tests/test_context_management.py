"""Tests for Tier 1, Tier 1.5, and Tier 2 context management."""

import pytest

from server.services.conversation_compactor import (
    ESSENTIAL_TOOLS,
    TOOL_PLACEHOLDERS,
    ConversationCompactor,
)
from server.services.conversation_pruner import ConversationPruner
from server.utils.model_limits import (
    get_compaction_trigger_tokens,
    get_handoff_trigger_tokens,
    get_model_context_limit,
    should_trigger_compaction,
    should_trigger_handoff,
)
from server.utils.token_estimator import count_exact, estimate_fast, estimate_messages_tokens_fast


class TestTokenEstimator:
    """Test token estimation utilities."""

    def test_estimate_fast(self):
        """Fast estimation should be ~4 chars per token."""
        text = "a" * 400  # 400 chars
        tokens = estimate_fast(text)
        assert 90 <= tokens <= 110  # Should be ~100 tokens (400/4)

    def test_count_exact_gpt4(self):
        """Exact counting should use tiktoken."""
        text = "Hello world, this is a test."
        tokens = count_exact(text, model="gpt-4")
        assert tokens > 0
        assert tokens < 50  # Should be around 8-10 tokens

    def test_estimate_messages_fast(self):
        """Fast message estimation should include overhead."""
        messages = [
            {"role": "user", "content": "test" * 100},  # ~400 chars
            {"role": "assistant", "content": "response" * 100},  # ~800 chars
        ]
        tokens = estimate_messages_tokens_fast(messages)
        assert tokens > 200  # At least content + overhead
        assert tokens < 400  # But not too much


class TestModelLimits:
    """Test model context limit registry."""

    def test_get_gpt4_limit(self):
        """GPT-4 should have 128k limit."""
        assert get_model_context_limit("gpt-4") == 128_000

    def test_get_claude_limit(self):
        """Claude should have 200k limit."""
        assert get_model_context_limit("claude-3-5-sonnet") == 200_000

    def test_strip_provider_prefix(self):
        """Should strip provider prefixes."""
        assert get_model_context_limit("openai/gpt-4") == 128_000
        assert get_model_context_limit("anthropic/claude-sonnet-4.5") == 200_000

    def test_should_trigger_handoff(self):
        """Handoff should trigger at 90% of limit."""
        # GPT-4: 128k limit, 90% = 115.2k
        assert should_trigger_handoff(120_000, "gpt-4") is True
        assert should_trigger_handoff(100_000, "gpt-4") is False

    def test_get_handoff_trigger_tokens(self):
        """Get handoff trigger threshold."""
        # GPT-4: 128k * 0.9 = 115.2k
        threshold = get_handoff_trigger_tokens("gpt-4")
        assert threshold == 115_200

    def test_should_trigger_compaction(self):
        """Compaction should trigger at 60% of limit."""
        # GPT-4: 128k limit, 60% = 76.8k
        assert should_trigger_compaction(80_000, "gpt-4") is True
        assert should_trigger_compaction(70_000, "gpt-4") is False

    def test_get_compaction_trigger_tokens(self):
        """Get compaction trigger threshold."""
        # GPT-4: 128k * 0.6 = 76.8k
        threshold = get_compaction_trigger_tokens("gpt-4")
        assert threshold == 76_800


class TestConversationPruner:
    """Test Tier 1 smart pruning."""

    def test_prune_old_tool_outputs(self):
        """Should prune tool outputs beyond protection zone when total tokens > 40k."""
        # Create enough conversation history with multiple old tool outputs
        # Protection zone = last 2 user messages (indices 10, 12)
        # So we need tool outputs BEFORE index 10 to be prunable
        items = [
            {"role": "user", "content": "Request 1"},
            {"role": "tool", "content": "A" * 200_000, "tool_call_id": "call_1"},  # OLD - should be pruned
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Request 2"},
            {"role": "tool", "content": "B" * 200_000, "tool_call_id": "call_2"},  # OLD - should be pruned
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Request 3"},
            {"role": "tool", "content": "C" * 200_000, "tool_call_id": "call_3"},  # OLD - should be pruned
            {"role": "assistant", "content": "Response 3"},
            {"role": "user", "content": "Request 4"},  # Start of protection zone (2nd to last user)
            {"role": "tool", "content": "D" * 200_000, "tool_call_id": "call_4"},  # PROTECTED - keep
            {"role": "assistant", "content": "Response 4"},
            {"role": "user", "content": "Request 5"},  # Last user message
            {"role": "tool", "content": "E" * 200_000, "tool_call_id": "call_5"},  # PROTECTED - keep
            {"role": "assistant", "content": "Response 5"},
        ]

        pruner = ConversationPruner()
        pruned_items, stats = pruner.prune(items, dry_run=False)

        # Should prune the old tool outputs (call_1, call_2, call_3)
        assert stats["outputs_pruned"] >= 2, f"Expected >=2 outputs pruned, got {stats['outputs_pruned']}"
        assert stats["tokens_saved"] > 0

        # The protected tool outputs should NOT be heavily pruned
        # call_4 is at index 10, call_5 is at index 13
        assert len(pruned_items[10]["content"]) > 150_000  # Still has most of content
        assert len(pruned_items[13]["content"]) > 150_000  # Still has most of content

    def test_skip_pruning_if_below_threshold(self):
        """Should skip pruning if savings < 20k tokens."""
        items = [
            {"role": "user", "content": "Request"},
            {"role": "tool", "content": "Small output", "tool_call_id": "call_1"},  # Too small
            {"role": "assistant", "content": "Response"},
        ]

        pruner = ConversationPruner()
        pruned_items, stats = pruner.prune(items, dry_run=False)

        assert stats["outputs_pruned"] == 0
        assert stats["pruning_performed"] is False

    def test_protection_zone_calculation(self):
        """Should protect last 2 user messages and everything after."""
        items = [
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "User 2"},  # Protection starts here
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "User 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        pruner = ConversationPruner()
        protection_start = pruner._find_protection_zone_start(items)

        # Should protect from index 2 onwards (User 2)
        assert protection_start == 2

    def test_dry_run_mode(self):
        """Dry run should calculate stats without modifying items."""
        items = [
            {"role": "user", "content": "Request"},
            {"role": "tool", "content": "A" * 10_000, "tool_call_id": "call_1"},
            {"role": "assistant", "content": "Response"},
        ]

        pruner = ConversationPruner()
        pruned_items, stats = pruner.prune(items, dry_run=True)

        # Items should be unchanged
        assert pruned_items == items
        # Stats should still be calculated
        assert "tokens_before" in stats
        assert "tokens_after" in stats

    def test_preserves_tool_call_id(self):
        """Pruned tool results should preserve tool_call_id field."""
        # Need enough history to trigger pruning (>40k tokens, outside protection zone)
        items = [
            {"role": "user", "content": "Request 1"},
            {"role": "assistant", "content": "Response 1", "tool_calls": [{"id": "call_1", "type": "function"}]},
            {"role": "tool", "content": "X" * 200_000, "tool_call_id": "call_1"},  # OLD - should be pruned
            {"role": "assistant", "content": "Done 1"},
            {"role": "user", "content": "Request 2"},
            {"role": "assistant", "content": "Response 2", "tool_calls": [{"id": "call_2", "type": "function"}]},
            {"role": "tool", "content": "Y" * 200_000, "tool_call_id": "call_2"},  # OLD - should be pruned
            {"role": "assistant", "content": "Done 2"},
            {"role": "user", "content": "Request 3"},  # Protection zone starts here (2nd to last user)
            {"role": "assistant", "content": "Response 3", "tool_calls": [{"id": "call_3", "type": "function"}]},
            {"role": "tool", "content": "Z" * 200_000, "tool_call_id": "call_3"},  # PROTECTED
            {"role": "assistant", "content": "Final"},
        ]

        pruner = ConversationPruner()
        pruned_items, stats = pruner.prune(items, dry_run=False)

        # At least one output should be pruned
        assert stats["outputs_pruned"] >= 1

        # Find the pruned tool results - check both index 2 (call_1) and 6 (call_2)
        pruned_tool_result_1 = pruned_items[2]

        # Should preserve tool_call_id even after pruning content
        assert "tool_call_id" in pruned_tool_result_1
        assert pruned_tool_result_1["tool_call_id"] == "call_1"
        assert pruned_tool_result_1["role"] == "tool"

        # Content should be truncated (much smaller than original 200k)
        assert len(pruned_tool_result_1["content"]) < 2000  # Truncated to ~1000 chars + placeholder message
        assert "Output pruned by Tier 1" in pruned_tool_result_1["content"]  # Has placeholder


class TestConversationCompactor:
    """Test Tier 1.5 conversation compaction with placeholders."""

    def test_placeholder_for_execute_query(self):
        """Should replace execute_*_query results with placeholder."""
        items = [
            {"role": "user", "content": "Run a query"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "execute_sql_query", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "A" * 10_000,  # Large result
                "tool_call_id": "call_1",
            },
            {"role": "assistant", "content": "Query completed"},
        ]

        compactor = ConversationCompactor()
        compacted, stats = compactor.compact(items, model="gpt-4", dry_run=False)

        # Tool result should be replaced with placeholder
        tool_result = compacted[2]
        assert "execute_sql_query" in tool_result["content"]
        assert "Use execute_sql_query again" in tool_result["content"]
        assert len(tool_result["content"]) < 200  # Much smaller than original

    def test_preserve_get_database_schema(self):
        """Should keep get_database_schema results in full."""
        items = [
            {"role": "user", "content": "Show schema"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_database_schema", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "Schema: " + "A" * 5_000,
                "tool_call_id": "call_1",
            },
            {"role": "assistant", "content": "Here's the schema"},
        ]

        compactor = ConversationCompactor()
        compacted, stats = compactor.compact(items, model="gpt-4", dry_run=False)

        # Essential tool result should NOT be replaced with placeholder but may be truncated
        tool_result = compacted[2]
        assert "Schema:" in tool_result["content"]
        assert len(tool_result["content"]) > 500  # Truncated to MAX_RESULT_PREVIEW_CHARS but not replaced

    def test_keep_only_latest_saved_query_schema(self):
        """Should keep only the most recent saved_query_schema."""
        items = [
            {"role": "user", "content": "First check"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "saved_query_schema", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "Old schema: version 1",
                "tool_call_id": "call_1",
            },
            {"role": "assistant", "content": "First result"},
            {"role": "user", "content": "Second check"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "saved_query_schema", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "Latest schema: version 2",
                "tool_call_id": "call_2",
            },
            {"role": "assistant", "content": "Second result"},
        ]

        compactor = ConversationCompactor()
        compacted, stats = compactor.compact(items, model="gpt-4", dry_run=False)

        # Old schema should be replaced with placeholder
        old_schema_result = compacted[2]
        assert (
            "saved_query_schema" in old_schema_result["content"].lower()
            or "Use saved_query_schema" in old_schema_result["content"]
        )

        # Latest schema should be kept
        latest_schema_result = compacted[6]
        assert "Latest schema: version 2" in latest_schema_result["content"]

    def test_tool_placeholders_are_informative(self):
        """Verify that placeholders guide the model to re-call if needed."""
        assert "execute_sql_query" in TOOL_PLACEHOLDERS
        assert "save_query" in TOOL_PLACEHOLDERS
        assert "get_existing_html" in TOOL_PLACEHOLDERS

        # All placeholders should guide the model on what to do next
        for tool_name, placeholder in TOOL_PLACEHOLDERS.items():
            has_guidance = (
                "again" in placeholder.lower()
                or "call" in placeholder.lower()
                or "use" in placeholder.lower()
                or "proceed" in placeholder.lower()
            )
            assert has_guidance, f"Placeholder for {tool_name} should guide next action"

    def test_essential_tools_defined(self):
        """Verify essential tools are correctly defined."""
        assert "get_database_schema" in ESSENTIAL_TOOLS
        assert "saved_query_schema" in ESSENTIAL_TOOLS


@pytest.mark.asyncio
class TestSessionIntegration:
    """Integration tests with ConversationStateSession."""

    async def test_prune_tool_outputs_integration(self):
        """Test Tier 1 pruning integration."""
        # This would test the actual session pruning
        # Requires setting up a real session with SQLite
        # Placeholder for now
        pass

    async def test_session_handoff_integration(self):
        """Test Tier 2 handoff integration."""
        # This would test the actual session handoff
        # Requires LLM connection for summarization
        # Placeholder for now
        pass
