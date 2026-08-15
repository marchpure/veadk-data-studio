DUCKDB_SPECIFIC_RULES = """
For query execution you should use tool execute_duckdb_query
1. ONLY SELECT statements – DuckDB queries must be read-only (no INSERT/UPDATE/DELETE/COPY/EXPORT/ATTACH/INSTALL/LOAD).
2. Reference uploaded files through their table aliases from the schema (for example: SELECT * FROM "orders").
3. NEVER include LIMIT/OFFSET clauses in the final query; rely on the tool limit for testing.
4. Quote identifiers with double quotes when they contain uppercase letters, spaces, or special characters.
5. Always provide explicit JOIN conditions to avoid accidental Cartesian joins.
6. Use DuckDB functions (e.g., CAST, COALESCE, date_trunc, json_extract) for type handling and semi-structured fields.
7. Handle NULL values explicitly with COALESCE/IFNULL when summarizing data.
8. Alias derived columns and aggregations for clarity.
9. Maintain read-only analysis—never attempt to modify files or DuckDB catalogs.

<critical>
- The query limit parameter supports up to 50 rows. During exploration/schema understanding, use 3-4 rows max. Only use higher limits when the analysis genuinely requires more rows.
- Try to aggregate the db queries if it fits the requirements, e.g, instead of listing rows try to aggregate numbers, like total or averages etc..
     only fetch larger number of rows if it's absolutely necessary. aggregation do help a lot. try to aggregate as much as possible
- Remember: using your best judgement, aggregations are the key to effective data summarization and visualization. Fetching lots of rows is not efficient do it if it's absolutely required.
</critical>

**Timeout Handling (30 second limit):**
- Queries timeout after 30 seconds. If "timeout": true in response, optimize the query immediately.
- Check "execution_time_seconds" vs "timeout_seconds" to gauge how close it was to completing.
- Optimize by: adding WHERE filters, using LIMIT, simplifying JOINs, using aggregates (COUNT/SUM/AVG), selecting fewer columns etc.
- After optimization, retry the query. If timeouts persist, fundamentally rethink your approach.
"""
