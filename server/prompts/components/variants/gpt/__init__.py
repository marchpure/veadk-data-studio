"""GPT-optimized prompt components.

This package contains prompt components specifically optimized for GPT models
(GPT-3.5, GPT-4, GPT-5.4, etc.).

Key optimizations for GPT models:
1. Markdown headers instead of XML tags
2. Positive framing ("Always do X" vs "Never do Y")
3. Explicit step-by-step sequences with clear boundaries
4. Reduced template embedding, more tool-based references
5. Flatter instruction hierarchies
6. Concrete examples with correct/incorrect patterns
"""

from server.prompts.components.variants.gpt.duck_db_specific_rules import (
    DUCKDB_SPECIFIC_RULES,
)
from server.prompts.components.variants.gpt.html_generation_rules import (
    HTML_DASHBOARD_RULES_TEMPLATE,
)
from server.prompts.components.variants.gpt.mongo_specific_rules import (
    MONGO_SPECIFIC_RULES,
)
from server.prompts.components.variants.gpt.query_output_format_rules import (
    QUERY_OUTPUT_RULES,
)
from server.prompts.components.variants.gpt.sql_rules import SQL_SPECIFIC_RULES
from server.prompts.components.variants.gpt.summary_after_code_generation import (
    SUMMARY_AFTER_CODE,
)

__all__ = [
    "HTML_DASHBOARD_RULES_TEMPLATE",
    "QUERY_OUTPUT_RULES",
    "SQL_SPECIFIC_RULES",
    "MONGO_SPECIFIC_RULES",
    "DUCKDB_SPECIFIC_RULES",
    "SUMMARY_AFTER_CODE",
]
