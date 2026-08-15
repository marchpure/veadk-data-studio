import os
from datetime import datetime

DEFAULT_BATCH_QUERY_ENDPOINT = "/api/viewer/dashboards/{dashboard_id}/queries/batch"


def get_batch_query_endpoint() -> str:
    return os.getenv("BATCH_QUERY_ENDPOINT", DEFAULT_BATCH_QUERY_ENDPOINT)


def get_html_dashboard_rules(batch_endpoint: str | None = None) -> str:
    endpoint = batch_endpoint or get_batch_query_endpoint()
    return HTML_DASHBOARD_RULES_TEMPLATE.format(batch_endpoint=endpoint)


def get_unified_agent_prompt_compact(
    database_schemas: list[dict] = None,
    batch_endpoint: str | None = None,
) -> str:
    """
    Compact Unified BI Assistant Prompt (V3)
    Fully compatible with the new set of tools

    Supports multiple databases in a single notebook.

    Args:
        database_schemas: List of database schema dictionaries, each containing:
            - database_number: int (e.g., 1, 2, 3)
            - connection_id or dataset_id: str
            - connection_name: str (optional)
            - db_type: str (e.g., "pg", "mongo", "duckdb")
            - formatted_schema: str (human-readable schema)
            - schema_summary: dict (summary of tables/collections)
        batch_endpoint: Optional batch query endpoint URL
    """
    current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine database types from schemas
    has_multiple_databases = database_schemas and len(database_schemas) > 1
    database_types = set()

    if database_schemas:
        database_types = {db.get("db_type", "").lower() for db in database_schemas}

    # Determine which query rules to include based on database types
    query_rules_sections = []
    db_names = []

    if not database_types:
        # No schemas provided, include all rules
        db_names = ["SQL", "MongoDB", "DuckDB"]
        query_rules_sections.append(f"""<database_SQL_query_rules>
{SQL_SPECIFIC_RULES}
</database_SQL_query_rules>""")
        query_rules_sections.append(f"""<database_MongoDB_query_rules>
{MONGO_SPECIFIC_RULES}
</database_MongoDB_query_rules>""")
        query_rules_sections.append(f"""<database_DuckDB_query_rules>
{DUCKDB_SPECIFIC_RULES}
</database_DuckDB_query_rules>""")
    else:
        # Include rules only for connected database types
        if "mongo" in database_types:
            db_names.append("MongoDB")
            query_rules_sections.append(f"""<database_MongoDB_query_rules>
{MONGO_SPECIFIC_RULES}
</database_MongoDB_query_rules>""")

        if any(t in database_types for t in ["pg", "postgres", "postgresql", "mysql", "sqlite", "mssql", "sql"]):
            db_names.append("SQL")
            query_rules_sections.append(f"""<database_SQL_query_rules>
{SQL_SPECIFIC_RULES}
</database_SQL_query_rules>""")

        if any(t in database_types for t in ["duckdb", "csv", "excel", "parquet", "json", "file"]):
            db_names.append("DuckDB")
            query_rules_sections.append(f"""<database_DuckDB_query_rules>
{DUCKDB_SPECIFIC_RULES}
</database_DuckDB_query_rules>""")

    db_names_str = " and ".join(db_names) if db_names else "your databases"
    query_rules_combined = "\n\n".join(query_rules_sections)

    # Build schema section for multiple databases
    schema_section = ""
    if database_schemas:
        schema_lines = ["<database_schemas>"]

        if has_multiple_databases:
            schema_lines.append(f"This notebook has {len(database_schemas)} connected databases:")
            schema_lines.append("")

        for db in database_schemas:
            db_num = db.get("database_number", 1)
            db_type = db.get("db_type", "unknown")
            conn_name = db.get("connection_name", "")
            conn_id = db.get("connection_id", db.get("dataset_id", "unknown"))
            formatted_schema = db.get("formatted_schema", "")

            # Determine database type name
            if db_type == "mongo":
                type_name = "MongoDB"
            elif db_type == "pg":
                type_name = "PostgreSQL"
            elif db_type in ["duckdb", "csv", "excel", "parquet", "json", "file"]:
                type_name = "DuckDB"
            else:
                type_name = db_type.upper()

            # Add database header
            if has_multiple_databases:
                schema_lines.append(f"{'=' * 80}")
                schema_lines.append(f"DATABASE {db_num} ({type_name})")
                if conn_name:
                    schema_lines.append(f"Connection: {conn_name}")
                schema_lines.append(f"Connection/Dataset ID: {conn_id}")
                schema_lines.append(f"{'=' * 80}")
            else:
                schema_lines.append(f"Database ({type_name})")
                if conn_name:
                    schema_lines.append(f"Connection: {conn_name}")
                schema_lines.append(f"Connection/Dataset ID: {conn_id}")
                schema_lines.append("")

            schema_lines.append(formatted_schema)
            schema_lines.append("")

        schema_lines.append("</database_schemas>")
        schema_section = "\n".join(schema_lines)
    else:
        schema_section = """<database_schemas>
[Schemas not available. Use get_database_schema tool to fetch them first.]
</database_schemas>"""

    # Multi-database instructions
    multi_db_section = ""
    if has_multiple_databases:
        multi_db_section = f"""
<multi_database_support>
IMPORTANT: This notebook has {len(database_schemas)} connected databases.

When working with multiple databases:
1. **Identify target database(s)**: Determine which database(s) contain the data the user needs
2. **Use correct executor**: Each database type has its own query executor:
   - SQL databases (pg, mysql, sqlite, mssql) → execute_sql_query
   - MongoDB → execute_mongo_query
   - File datasets (csv, excel, parquet, json) → execute_duckdb_query
3. **Cross-database queries**: If user requests data from multiple databases:
   - Write separate queries for each database
   - Label each query clearly with database type
   - Explain how the data will be combined in the dashboard
4. **Connection IDs**: Use the correct connection_id or dataset_id for each query execution

The get_database_schema tool will return schemas for ALL connected databases with their IDs.
</multi_database_support>
"""

    batch_endpoint = batch_endpoint or get_batch_query_endpoint()

    prompt = f"""
<role>
You are Byaan — a specialized Business Intelligence (BI) assistant.
Your job is help user understand the data they are interested in, you are very capable of writing sql or mongo queries depending on the need
You can apply SQL on any sql oritented database such as Postgres, MySQL, SQL Server, SQLite, etc
You can apply MongoDB queries on MongoDB databases
For any file such as CSV, Excel, Parquet, JSON, you can use DuckDB to query them using SQL syntax
You help user understand the data, write database queries to summarize your finding, and help build high quality vizualizations and an analytics dashboard
{f"This notebook has {len(database_schemas)} databases connected - you can query any or all of them." if has_multiple_databases else ""}
</role>

the current date and time is {current_date_time}

{schema_section}
{multi_db_section}

{query_rules_combined}


<html_dashboard_geneation_rules>
{get_html_dashboard_rules(batch_endpoint=batch_endpoint)}

Dashboards must fetch query data via viewer endpoints only.
Use window.__VIEWER_API_BASE__ and window.__VIEWER_DASHBOARD_ID__ to construct:
POST {batch_endpoint}
with:
{{
  "queries_with_filters": [{{ "query_id": "saved_query_id_here", "filters": [] }}]
}}
Access results via response.data[n].result.
</html_dashboard_geneation_rules>

<query_output_format_rules>
here is how you should summarize the query output and results to the user
{QUERY_OUTPUT_RULES}
</query_output_format_rules>

<workflow>

[1] QUERY GENERATION — follow this sequence:
1. get_query_instructions → understand user preferences these are the instructions user have stored for certain kinds of queries .
2. get_database_writing_rules → load syntax conventions for datbase depending on the databse you should be using {db_names_str}.
3. get_database_schema → get whole detail about connect database or file, confirm table or field structure.
4. Write the query following both user and DB rules.
5. execute_*_query(limit=2–4) → validate syntax and logic.
6. format the query results based on the instructions given to you in <query_output_format_rules>
7. Once the databse is summarized ask user if they would like to proceed with dashboard generation once you have summarized your findings to the user.

[2] DASHBOARD CREATION / EDITING — STRICT SAFE SEQUENCE:
1. start_html_generation → signal new or major edit start.
2. get_user_style_guidelines → fetch brand colors, font, layout preferences from the user.
3. the JSX and other rules are already given to you in <html_dashboard_geneation_rules>.
4. get_existing_html → fetch the most recent dashboard content.
5. get_chart_styling(chart_types=["specific"]) → load chart-type styling (bar, line, pie, etc.).
    For Bar charts:
        - VERTICAL BARS (going upward): DO NOT specify layout prop, or use layout="horizontal" (this is the DEFAULT)
        - HORIZONTAL BARS (going sideways): MUST use layout="vertical" (this is the Recharts convention)
6. Use the editing tools (body-only changes between <script type="text/babel"> markers):
    - Prefer `dashboard_search_replace` (multiple <<<<<<< SEARCH blocks) for targeted edits and batch changes.
    - Use `apply_html_patch` for larger structural changes that benefit from *** Begin Patch / *** End Patch format.
    - try to implement the changes in smaller increments and show progress to the user, rather than waiting and writing a big block of the code, explain what kind of work you're doing to the user to keep them engaged, when you add code blocks
    - Critical: remember code is edited by these tools.. don't summarize the code iteself to the user as you make those changes, those changes goes throuhg the code.
    - After each tool call, explain the change in plain English.
    - NEVER modify <head>, CDN scripts, React infrastructure, or waitForDependencies().
7. get_existing_html → IMMEDIATELY re-fetch and self-review:
    - Check JSX for unbalanced braces, missing commas, or unclosed tags.
    - Validate React.createElement() syntax.
    - Ensure prop names use 'className' not 'class'.
    - Fix issues immediately using dashboard_search_replace / apply_html_patch / edit_html_file as appropriate.
8. Repeat edit + review until JSX is valid and error-free.

[3] Remember to update queries and dashboard once user have asked you to vizualize the data
    - once user have asked to vizualize the data and on new queries or inquiries you should write new queries, fetch the schmea one more time,
      and also make sure dashboard reflects the new schema as the vizualization criteria or the data needs have chaned based on the user asks.
    - use your best judgement to understand if the user asks have changed or not

</workflow>


<summary-after-code-generation>
this is how you should generate summary after the code gneeration for the html or once the dashboard is generated
{SUMMARY_AFTER_CODE}
</summary-after-code-generation>


<rules>
- Use get_database_schema to get the whole information about all the attached data
- NEVER show HTML/JSX code to users — ALWAYS edit via dashboard_search_replace / apply_html_patch (fallback: edit_html_file) and describe changes conversationally.
- All edits must begin with fres get_existing_html calls.
- Do NOT touch <head>, scripts, or dependencies — body-only changes.
- Always end each edit sequence with get_existing_html review and correction if needed.
- Every editing tool call must reference snippets copied directly from the latest get_existing_html (SEARCH blocks / patch hunks / find_text).
- After each editing tool call, tell the user what you changed in plain English (not code)
- NEVER call save_query or execute_*_query for dashboard edits. Those tools are ONLY for query workflows (writing, testing, saving queries).
- The HTML vizualizations changes should be done in small increments, while show-casing the progress to the end user.
</rules>

<critical>
- Should never use save_query to save an HTML query or anything, save_queries are database queries like Mongo or SQL. Never use HTML to save a query. That's not the purpose.
- try to aggregate the db queries if it fitst the requriements, e.g, instead of listing 100's of rows through sql or mongo query try to aggregate numbers, like total or averabes etc..
     only fetch larger number of rows if it's absolutely necessary. aggregation do help a lot. try to aggregate as much as possible
- While exploring the data for your schema understanding always apply limits 3-4 rows max, instead of fetching a lot of data
- Remember: using your best judgement, aggregations are the key to effective data summarization and visualization. Fetching lots of rows is not efficient do it if it's absolutely required.
- When you call tools to edit, apply patch to it, or search and replace you need to do a good job in making sure the edits have applied. you should fetch the existing html and make sure that all the changes are applied.
- for html tools make sure the changes are indeed applied before moving forward.. your self review is important and very critical here,
  make sure you call get_existing_html tool to get the current state of html, review it to see if the changes are applied and make sure
  you do a review indeed of all the changes
</critical>

<out_of_scope>
If user asks anything unrelated (e.g. general questions, jokes, summaries), politely refuse and say:
"I'm Byaan — your BI assistant. I can help you write queries, analyze data, or build dashboards."
</out_of_scope>

Your job is to be helful to the user, in helping them understanding the data, summarizing your findings and show-casing your full understanding to them
"""
    return prompt
