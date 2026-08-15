DYNAMODB_SPECIFIC_RULES = """
For query execution use tool execute_dynamodb_query.
The schema header shows the connection's query mode: (mode:partiql) or (mode:native). Use the matching syntax.

<partiql_mode>
When schema shows (mode:partiql), use SQL-like PartiQL syntax:
1. ONLY SELECT statements — no INSERT, UPDATE, DELETE.
2. Always double-quote table and attribute names: SELECT "name", "email" FROM "Users"
3. Filter by partition key for efficient queries: SELECT * FROM "Orders" WHERE "userId" = 'abc123'
4. No JOINs — each table is independent. Query one table at a time.
5. No GROUP BY, COUNT(), SUM(), AVG() — DynamoDB has no server-side aggregation. Fetch rows and summarize client-side.
6. No LIKE — use contains() or begins_with(): WHERE contains("name", 'john')
7. Nested attribute access: SELECT "address"."city" FROM "Users"
8. Use limit parameter in tool (not LIMIT in query) for testing.
</partiql_mode>

<native_mode>
When schema shows (mode:native), pass JSON operation specs as the query string:
1. Only read operations allowed: scan, query, get_item, batch_get_item, describe_table
2. scan — full table read: {"operation": "scan", "table": "Users"}
3. query — key-based lookup: {"operation": "query", "table": "Orders", "key_condition_expression": "userId = :uid", "expression_attribute_values": {":uid": {"S": "abc123"}}}
4. get_item — single item: {"operation": "get_item", "table": "Users", "key": {"userId": {"S": "abc123"}}}
5. describe_table — table metadata: {"operation": "describe_table", "table": "Users"}
6. Optional fields: filter_expression, expression_attribute_names, expression_attribute_values, projection_expression, index_name
7. Values must use DynamoDB type descriptors: {"S": "string"}, {"N": "123"}, {"BOOL": true}
</native_mode>

Use save_query to save DynamoDB queries for dashboards, same workflow as SQL or MongoDB.
For dashboards with filters, PartiQL mode is preferred since filter injection works with SQL-compatible WHERE clauses.

<critical>
- The query limit parameter supports up to 50 rows. During exploration/schema understanding, use 3-4 rows max. Only use higher limits when the analysis genuinely requires more rows.
- DynamoDB has no server-side aggregation — fetch minimal rows and summarize client-side.
</critical>

<timeout_handling>
- Queries timeout after 30 seconds. If "timeout": true in response, optimize the query immediately.
- Optimize by: adding partition key filters, reducing result set with more specific WHERE conditions, lowering limit.
- Full table scans on large tables will timeout — always filter by key attributes.
</timeout_handling>
"""
