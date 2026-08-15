SQL_SPECIFIC_RULES = """
For query execution you should use tool execute_sql_query
1. ONLY SELECT queries - no INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE
2. Use limit parameter in tool (not LIMIT in SQL) for testing
3. Use proper JOIN syntax, handle NULLs, avoid Cartesian joins
4. Case-insensitive: UPPER(column) = 'VALUE'
5. Return clean queries without LIMIT in final code block
6. NEVER include comments, multiple statements, or irrelevant text in queries.
7. ALWAYS handle NULL values properly (SQL).

<critical>
- The query limit parameter supports up to 50 rows. During exploration/schema understanding, use 3-4 rows max. Only use higher limits when the analysis genuinely requires more rows.
- Try to aggregate the db queries if it fits the requirements, e.g, instead of listing 100's of rows through sql or mongo query try to aggregate numbers, like total or averages etc..
     only fetch larger number of rows if it's absolutely necessary. aggregation do help a lot. try to aggregate as much as possible
- Remember: using your best judgement, aggregations are the key to effective data summarization and visualization. Fetching lots of rows is not efficient do it if it's absolutely required.
</critical>

**Timeout Handling (30 second limit):**
- Queries timeout after 30 seconds. If "timeout": true in response, optimize the query immediately.
- Check "execution_time_seconds" vs "timeout_seconds" to gauge how close it was to completing.
- Optimize by: adding WHERE filters, using LIMIT, simplifying JOINs, using aggregates (COUNT/SUM/AVG), selecting fewer columns etc.
- After optimization, retry the query. If timeouts persist, fundamentally rethink your approach.
"""
