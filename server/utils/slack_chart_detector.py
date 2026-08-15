"""LLM-based chart detection and generation for Slack responses."""

from __future__ import annotations

import json
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.services.completion_service import CompletionService
from server.services.slack_chart_service import ChartService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class SlackChartDetector:
    """LLM-based chart detection and generation for Slack responses."""

    @staticmethod
    async def generate_chart_with_llm(
        text: str,
        llm_connection_id: str,
        session: AsyncSession,
    ) -> list[str]:
        """
        Use LLM to analyze all tables and generate chart configurations.

        Args:
            text: Response text containing markdown tables
            llm_connection_id: LLM connection UUID
            session: Database session

        Returns:
            List of chart image URLs (one per table, empty list if none generated)
        """
        all_tables = SlackChartDetector._extract_all_tables(text)
        if not all_tables:
            logger.info("LLM chart: no tables found")
            return []

        chart_urls = []
        for idx, rows in enumerate(all_tables):
            logger.info(f"Processing table {idx + 1}/{len(all_tables)} with {len(rows) - 1} data rows")

            try:
                table_preview = "\n".join([" | ".join(row) for row in rows[: min(len(rows), 25)]])

                prompt = f"""Analyze this data table and determine the best chart configuration.

TABLE:
{table_preview}

Your task:
1. Identify which column should be used for labels (X-axis)
2. Identify which columns contain numeric data suitable for plotting (Y-axis):
   - Ignore units like "min", "$", "%", etc. in values
   - Ignore row numbers, index columns (e.g., 1, 2, 3, 4, 5...) etc.
   - Focus on meaningful metrics.
3. Choose the most appropriate chart type based on the data characteristics and what story it tells

Available chart types:
- bar_chart: vertical bars for categorical comparisons
- horizontal_bar_chart: horizontal bars (useful for long category names)
- stacked_bar_chart: stacked vertical bars showing part-to-whole across categories
- grouped_bar_chart: side-by-side vertical bars comparing metrics
- line_chart: time series, trends, or continuous data
- pie_chart: part-to-whole relationships (single dataset only)
- donut_chart: like pie with center hole (single dataset only)
- scatter_plot: relationship between two variables (X-Y coordinates)
- radar_chart: multivariate data across multiple dimensions

Return ONLY a JSON object in this exact format:
{{"labels_col": 0, "series_cols": [1, 2], "type": "bar_chart"}}

Where:
- labels_col: column index for X-axis labels (0-based)
- series_cols: array of column indexes for Y-axis data (0-based)
- type: one of the chart types listed above

If the table cannot be charted (no numeric data, all IDs or sequential numbers, etc), return:
{{"error": "reason"}}"""

                result = await CompletionService.complete(
                    prompt=prompt,
                    llm_connection_id=UUID(llm_connection_id),
                    session=session,
                    system_prompt="You analyze data tables and determine the best chart configuration. Focus on meaningful metrics and reject tables with only metadata or row numbers. Return only valid JSON, no markdown or explanations.",
                )

                if not result or not result.strip():
                    logger.info(f"LLM chart table {idx + 1}: empty response from LLM")
                    continue

                cleaned_result = result.strip()
                cleaned_result = cleaned_result.strip("`")
                cleaned_result = cleaned_result.replace("```json", "").replace("```", "")
                if cleaned_result.startswith("json"):
                    cleaned_result = cleaned_result[4:]
                cleaned_result = cleaned_result.strip()

                if not cleaned_result:
                    logger.info(
                        f"LLM chart table {idx + 1}: response became empty after cleaning. Original: '{result[:100]}'"
                    )
                    continue

                try:
                    config = json.loads(cleaned_result)
                except json.JSONDecodeError as e:
                    logger.info(
                        f"LLM chart table {idx + 1}: invalid JSON from LLM. Error: {e}. Response: '{cleaned_result[:200]}'"
                    )
                    continue

                if "error" in config:
                    logger.info(f"LLM chart table {idx + 1}: {config['error']}")
                    continue

                labels_col_idx = config["labels_col"]
                series_col_indices = config["series_cols"]
                llm_chart_type = config["type"]

                chart_type_mapping = {
                    "bar_chart": "bar",
                    "horizontal_bar_chart": "horizontalBar",
                    "stacked_bar_chart": "bar",
                    "grouped_bar_chart": "bar",
                    "line_chart": "line",
                    "pie_chart": "pie",
                    "donut_chart": "doughnut",
                    "scatter_plot": "scatter",
                    "radar_chart": "radar",
                }

                chart_type = chart_type_mapping.get(llm_chart_type, "bar")

                logger.info(
                    f"LLM chart table {idx + 1} decision: labels_col={labels_col_idx}, series_cols={series_col_indices}, type={llm_chart_type} -> {chart_type}"
                )

                data_rows = rows[1:]
                labels = [
                    row[labels_col_idx] if labels_col_idx < len(row) else f"Row {i + 1}"
                    for i, row in enumerate(data_rows)
                ]

                datasets = []
                for col_idx in series_col_indices:
                    if col_idx >= len(rows[0]):
                        continue

                    col_name = rows[0][col_idx] if col_idx < len(rows[0]) else f"Series {col_idx}"
                    values = []
                    for row in data_rows:
                        if col_idx < len(row):
                            try:
                                # Clean numeric value for charting (remove formatting and units)
                                cleaned = str(row[col_idx])
                                cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "").replace("¥", "")
                                cleaned = cleaned.replace("%", "").replace(",", "")
                                for unit in [
                                    " minutes",
                                    " mins",
                                    " min",
                                    " hours",
                                    " hrs",
                                    " hr",
                                    " seconds",
                                    " secs",
                                    " sec",
                                    " days",
                                    " day",
                                    " weeks",
                                    " week",
                                    " months",
                                    " month",
                                    " years",
                                    " year",
                                    " kg",
                                    " km",
                                    " mi",
                                    " ft",
                                    " m",
                                    " cm",
                                ]:
                                    cleaned = cleaned.replace(unit, "")
                                cleaned = cleaned.strip()
                                val = float(cleaned)
                                values.append(val)
                            except (ValueError, AttributeError):
                                values.append(None)
                        else:
                            values.append(None)

                    datasets.append(
                        {
                            "label": col_name,
                            "data": values,
                        }
                    )

                if not datasets:
                    logger.info(f"LLM chart table {idx + 1}: no valid datasets")
                    continue

                logger.info(f"LLM chart table {idx + 1} labels: {labels[:10]}{'...' if len(labels) > 10 else ''}")
                for ds in datasets:
                    logger.info(
                        f"LLM chart table {idx + 1} dataset '{ds['label']}': {ds['data'][:10]}{'...' if len(ds['data']) > 10 else ''}"
                    )

                chart_url = ChartService.generate_chart_url(
                    chart_type=chart_type,
                    labels=labels,
                    datasets=datasets,
                )

                logger.info(
                    f"LLM chart table {idx + 1} generated: {chart_type} with {len(datasets)} datasets, URL length: {len(chart_url)}"
                )
                chart_urls.append(chart_url)

            except Exception as e:
                logger.error(f"LLM chart generation failed for table {idx + 1}: {e}", exc_info=True)
                continue

        return chart_urls

    @staticmethod
    def should_generate_chart(text: str) -> bool:
        """Check if text contains chartable markdown tables."""
        if not SlackChartDetector._has_markdown_table(text):
            logger.info("Chart check: no markdown table found")
            return False

        all_tables = SlackChartDetector._extract_all_tables(text)
        if not all_tables:
            logger.info("Chart check: no valid tables found")
            return False

        logger.info(f"Chart check: found {len(all_tables)} chartable table(s)")
        return True

    @staticmethod
    def _has_markdown_table(text: str) -> bool:
        pattern = r"\|[^|\n]+\|[^|\n]+\|[\r\n]+\|[^|\n]+\|[^|\n]+\|"
        return bool(re.search(pattern, text))

    @staticmethod
    def _extract_all_tables(text: str) -> list[list[list[str]]]:
        """Extract all markdown tables as list of row arrays."""
        pattern = r"(\|[^\n]+\|(?:[\r\n]+\|[^\n]+\|)+)"
        matches = re.finditer(pattern, text)

        all_tables = []
        for match in matches:
            lines = [ln.strip() for ln in match.group(1).strip().split("\n") if ln.strip()]
            rows: list[list[str]] = []
            for line in lines:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if cells and all(re.match(r"^[\s:-]+$", c) for c in cells):
                    continue
                cells = [SlackChartDetector._clean_cell(c) for c in cells]
                if cells:
                    rows.append(cells)
            if len(rows) >= 2:
                all_tables.append(rows)

        return all_tables

    @staticmethod
    def _clean_cell(cell: str) -> str:
        """Clean cell content by removing emojis and extra whitespace."""
        cell = re.sub(r":[\w+-]+:", "", cell)
        cell = re.sub(r"[\U0001F300-\U0001F9FF]", "", cell)
        cell = re.sub(r"[\U0001F600-\U0001F64F]", "", cell)
        cell = re.sub(r"[\U0001F680-\U0001F6FF]", "", cell)
        cell = re.sub(r"[\U00002600-\U000027BF]", "", cell)
        cell = re.sub(r"[\U0001F1E0-\U0001F1FF]", "", cell)
        cell = re.sub(r"\s+", " ", cell).strip()
        return cell if cell else "-"
