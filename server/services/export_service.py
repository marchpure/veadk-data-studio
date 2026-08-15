import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from server.services.notebook import NotebookService
from server.services.query_service import QueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class CompiledHtmlExportService:
    """Service for generating standalone compiled HTML with embedded data."""

    @staticmethod
    def extract_query_ids_from_html(html_content: str) -> list[str]:
        """
        Extract all query IDs from fetch API calls in the HTML.

        Looks for patterns like:
        - queries_with_filters: [{ query_id: "uuid-here", ... }]
        - query_ids: ["uuid-1", "uuid-2"]

        Args:
            html_content: The HTML content to parse

        Returns:
            List of unique query IDs found in the HTML
        """
        try:
            query_ids = set()

            # Pattern 1: queries_with_filters array with query_id properties
            # Matches: { query_id: "..." } or { "query_id": "..." }
            pattern1 = r'query_id["\']?\s*:\s*["\']([a-f0-9\-]+)["\']'
            matches1 = re.findall(pattern1, html_content, re.IGNORECASE)
            query_ids.update(matches1)

            # Pattern 2: query_ids array
            # Matches: ["uuid-1", "uuid-2"] or ['uuid-1', 'uuid-2']
            pattern2 = r'query_ids["\']?\s*:\s*\[(.*?)\]'
            matches2 = re.findall(pattern2, html_content, re.DOTALL)
            for match in matches2:
                # Extract individual UUIDs from the array
                uuid_pattern = r'["\']([a-f0-9\-]{36})["\']'
                uuids = re.findall(uuid_pattern, match)
                query_ids.update(uuids)

            logger.info(f"Extracted {len(query_ids)} unique query IDs from HTML")
            return list(query_ids)
        except Exception as e:
            logger.error(
                f"Failed to extract query IDs from HTML: {str(e)}",
                posthog_context={"function": "CompiledHtmlExportService.extract_query_ids_from_html"},
            )
            raise

    @staticmethod
    async def execute_queries_and_collect_data(session: AsyncSession, query_ids: list[str]) -> dict[str, Any]:
        """
        Execute all queries and collect their results.

        Args:
            session: Database session
            query_ids: List of query IDs to execute

        Returns:
            Dictionary mapping query_id to result data
        """
        try:
            if not query_ids:
                logger.info("No query IDs to execute")
                return {}

            logger.info(f"Executing {len(query_ids)} queries")

            # Execute all queries in batch
            result = await QueryService.execute_batch_saved_queries(
                session=session, query_ids=query_ids, max_parallel=5
            )

            # Build a map of query_id -> result
            query_data_map = {}
            if result.get("success") or result.get("partial_success"):
                for query_result in result.get("data", []):
                    query_id = query_result.query_id
                    if query_result.success:
                        query_data_map[query_id] = {
                            "success": True,
                            "data": query_result.result,
                            "query_name": query_result.query_name,
                            "execution_time_ms": query_result.execution_time_ms,
                        }
                    else:
                        query_data_map[query_id] = {
                            "success": False,
                            "error": query_result.error,
                            "query_name": query_result.query_name,
                        }

            logger.info(f"Successfully executed {len(query_data_map)} queries")
            return query_data_map
        except Exception as e:
            logger.error(
                f"Failed to execute queries and collect data: {str(e)}",
                posthog_context={
                    "function": "CompiledHtmlExportService.execute_queries_and_collect_data",
                    "query_count": len(query_ids),
                },
            )
            raise

    @staticmethod
    def embed_data_in_html(html_content: str, query_data_map: dict[str, Any]) -> str:
        """
        Embed query results into HTML as inline JavaScript data.

        Args:
            html_content: Original HTML content
            query_data_map: Map of query_id to result data

        Returns:
            Modified HTML with embedded data
        """
        # Create embedded data script
        embedded_data_script = f"""
<script>
// Embedded data generated at export time
window.__EMBEDDED_DATA__ = {{
    query_results: {json.dumps(query_data_map, indent=2, default=str)},
    generated_at: "{CompiledHtmlExportService._get_timestamp()}",
    is_compiled: true
}};

// Helper function to get query result by ID
window.getEmbeddedQueryResult = function(queryId) {{
    return window.__EMBEDDED_DATA__.query_results[queryId] || null;
}};
</script>
"""

        # Insert the embedded data script right after <head> tag
        if "<head>" in html_content.lower():
            # Find the position after <head>
            head_pos = html_content.lower().find("<head>") + len("<head>")
            html_content = html_content[:head_pos] + embedded_data_script + html_content[head_pos:]
        else:
            # If no head tag, insert at the beginning
            html_content = embedded_data_script + html_content

        logger.info("Embedded data script injected into HTML")
        return html_content

    @staticmethod
    def remove_api_calls(html_content: str, disable_animations: bool = False) -> str:
        """
        Replace fetch API calls with synchronous data access from embedded data.

        This replaces fetch calls to /api/queries/batch with immediate data access
        from window.__EMBEDDED_DATA__.

        Args:
            html_content: HTML content with embedded data

        Returns:
            Modified HTML with API calls replaced
        """
        # Strategy: Replace fetch calls with a function that returns embedded data

        # Create a wrapper script that overrides fetch for the queries endpoint
        fetch_override_script = """
<script>
// Override fetch for compiled HTML mode
(function() {
    const originalFetch = window.fetch;

    window.fetch = function(url, options) {
        // Check if this is a queries/batch API call
        if (typeof url === 'string' && (url.includes('/api/queries/batch') || url.includes('/queries/batch'))) {
            console.log('[Compiled HTML] Intercepting API call, using embedded data');

            // Parse the request body to get query IDs
            if (options && options.body) {
                try {
                    const requestData = JSON.parse(options.body);
                    const queryIds = requestData.query_ids || [];
                    const queriesWithFilters = requestData.queries_with_filters || [];

                    // Collect results from embedded data
                    const results = [];

                    // Handle query_ids format
                    if (queryIds.length > 0) {
                        for (const queryId of queryIds) {
                            const embeddedResult = window.getEmbeddedQueryResult(queryId);
                            if (embeddedResult) {
                                results.push({
                                    query_id: queryId,
                                    query_name: embeddedResult.query_name || 'Unknown',
                                    success: embeddedResult.success,
                                    result: embeddedResult.data || null,
                                    error: embeddedResult.error || null,
                                    execution_time_ms: embeddedResult.execution_time_ms || 0
                                });
                            }
                        }
                    }

                    // Handle queries_with_filters format
                    if (queriesWithFilters.length > 0) {
                        for (const queryItem of queriesWithFilters) {
                            const queryId = queryItem.query_id;
                            const embeddedResult = window.getEmbeddedQueryResult(queryId);
                            if (embeddedResult) {
                                results.push({
                                    query_id: queryId,
                                    query_name: embeddedResult.query_name || 'Unknown',
                                    success: embeddedResult.success,
                                    result: embeddedResult.data || null,
                                    error: embeddedResult.error || null,
                                    execution_time_ms: embeddedResult.execution_time_ms || 0
                                });
                            }
                        }
                    }

                    // Return a mock Response object
                    const mockResponse = {
                        success: true,
                        message: 'Data loaded from embedded source',
                        data: results,
                        partial_success: false,
                        total_queries: results.length,
                        successful_queries: results.filter(r => r.success).length,
                        failed_queries: results.filter(r => !r.success).length,
                        total_execution_time_ms: 0
                    };

                    return Promise.resolve({
                        ok: true,
                        status: 200,
                        json: () => Promise.resolve(mockResponse),
                        text: () => Promise.resolve(JSON.stringify(mockResponse))
                    });
                } catch (error) {
                    console.error('[Compiled HTML] Error processing embedded data:', error);
                    return Promise.reject(error);
                }
            }
        }

        // For all other requests, use original fetch
        return originalFetch.apply(this, arguments);
    };

    // Set pdfDataReady flag after page fully loads (for screenshot service)
window.addEventListener('load', function() {
    // Give it a tiny moment for the charts to initialize
    requestAnimationFrame(() => {
        setTimeout(() => {
            window.pdfDataReady = true;
        }, 500); // 500ms is usually enough if animations are disabled
    });
});
})();
</script>
"""

        # Insert the fetch override script after the embedded data script
        # Look for the end of the embedded data script tag
        if "window.__EMBEDDED_DATA__" in html_content:
            # Find the closing script tag after embedded data
            embedded_data_pos = html_content.find("window.__EMBEDDED_DATA__")
            script_close_pos = html_content.find("</script>", embedded_data_pos)

            if script_close_pos != -1:
                insert_pos = script_close_pos + len("</script>")
                html_content = html_content[:insert_pos] + fetch_override_script + html_content[insert_pos:]
                logger.info("Fetch override script injected into HTML")

        # Disable Recharts animations only for Puppeteer screenshot compatibility
        if disable_animations:
            html_content = html_content.replace("isAnimationActive={true}", "isAnimationActive={false}")

            import re

            recharts_components = [
                "BarChart",
                "LineChart",
                "AreaChart",
                "PieChart",
                "ScatterChart",
                "RadarChart",
                "ComposedChart",
                "Bar",
                "Line",
                "Area",
                "Pie",
                "Scatter",
                "Radar",
                "Treemap",
                "RadialBarChart",
            ]

            for component in recharts_components:
                html_content = re.sub(
                    f"<{component}(\\s+(?![^>]*isAnimationActive))",
                    f"<{component} isAnimationActive={{false}}\\1",
                    html_content,
                )

            logger.info("Disabled Recharts animations for screenshot mode")

        print_styles = """
<style>
@media print {
    /* Let the dashboard breathe at its natural width */
    body {
        width: auto !important;
        overflow-x: hidden !important;
    }

    /* Ensure charts and tiles don't get split across pages */
    .dashboard-tile, .chart-container, .recharts-wrapper, .card {
        break-inside: avoid !important;
        page-break-inside: avoid !important;
        display: block !important;
        position: relative !important;
    }
}
</style>
"""
        # Inject the styles into the <head> if it exists, otherwise just append
        if "</head>" in html_content.lower():
            html_content = html_content.replace("</head>", f"{print_styles}</head>")
        else:
            html_content += print_styles

        logger.info("Print styles for page-break avoidance injected")

        return html_content

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime

        return datetime.utcnow().isoformat() + "Z"

    @staticmethod
    async def generate_compiled_html(
        session: AsyncSession, notebook_id: str, version: int | None = None, disable_animations: bool = False
    ) -> str:
        """
        Generate a compiled HTML file with all data embedded.

        This is the main entry point that orchestrates:
        1. Fetching the HTML content
        2. Extracting query IDs
        3. Executing queries
        4. Embedding data
        5. Replacing API calls

        Args:
            session: Database session
            notebook_id: Notebook ID
            version: Optional version number to export (defaults to latest)

        Returns:
            Compiled HTML string with embedded data

        Raises:
            ValueError: If notebook or HTML content not found
        """
        try:
            logger.info(
                f"Generating compiled HTML for notebook {notebook_id}"
                + (f" version {version}" if version else " (latest)")
            )

            # Step 1: Get the HTML content
            html_content = await NotebookService.get_notebook_html_content(session, notebook_id, version)
            if not html_content:
                raise ValueError(f"No HTML content found for notebook {notebook_id}")

            # Step 2: Extract query IDs from the HTML
            query_ids = CompiledHtmlExportService.extract_query_ids_from_html(html_content)

            # Step 3: Execute all queries and collect data
            query_data_map = await CompiledHtmlExportService.execute_queries_and_collect_data(session, query_ids)

            # Step 4: Embed data into HTML
            html_content = CompiledHtmlExportService.embed_data_in_html(html_content, query_data_map)

            # Step 5: Replace API calls with embedded data access
            html_content = CompiledHtmlExportService.remove_api_calls(html_content, disable_animations)

            logger.info(f"Successfully generated compiled HTML for notebook {notebook_id}")
            return html_content
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to generate compiled HTML: {str(e)}",
                posthog_context={
                    "function": "CompiledHtmlExportService.generate_compiled_html",
                    "notebook_id": notebook_id,
                    "version": version,
                },
            )
            raise
