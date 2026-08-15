FILTER_WORKFLOW_RULES = """
*** FILTER METADATA IS REQUIRED, IN-DASHBOARD FILTER UI IS FORBIDDEN ***

Dashboard filters are now rendered by the host application (outside iframe), not by generated dashboard HTML.
Your responsibility is to define and maintain filter metadata only.

STEP 0: LOAD EXISTING FILTER METADATA FIRST
   Call get_dashboard_filter_config() before creating new filters.
   - If has_filters = true: reuse/update/remove only as needed (avoid duplicates).
   - If has_filters = false: continue with discovery and definition.
   - NOTE: filters may already be auto-inferred after save_query(..., is_dashboard=true).

STEP 1: IDENTIFY FILTERABLE SOURCE COLUMNS (REQUIRED)
   IMPORTANT: Filters compile into SQL/Mongo predicates on source fields.
   - Use only source table/collection fields.
   - Never use SELECT aliases or computed-only output fields.
   - For JOIN SQL queries, use table-qualified names (e.g., "g.name").
   - For MongoDB $lookup aggregations, filter on the localField (source foreign key), NOT the joined/unwound result fields.

   Example SQL:
   "SELECT category, SUM(amount) AS total FROM orders GROUP BY category"
   - filterable: category
   - not filterable: total

   Example MongoDB:
   db.collection1.aggregate([{$lookup: {from: "collection2", localField: "ref_id", foreignField: "_id", as: "joined_data"}}, {$unwind: "$joined_data"}])
   - filterable: ref_id (the source field)
   - not filterable: joined_data.field (result of $lookup, doesn't exist when filter is applied)

   CRITICAL MONGODB AGGREGATION FILTER RULE:
   When using $lookup aggregations, filters MUST operate on fields from the BASE collection, not the joined result:
   - Use the localField (foreign key in base collection) as the filter field_name
   - Use label-value mapping to show human-readable values: [{"label": "...", "value": foreign_key_value}, ...]
   - Query the referenced collection separately to build the label-value pairs
   - Never filter on fields accessed through joined/unwound documents (dotted paths like "joined.field")

   Incorrect: field_name="joined_doc.display_field", value="display_text"
   Correct: field_name="fk_field", options=[{"label": "display_text", "value": fk_value}, ...]

STEP 2: CALL get_filter_options FOR EACH CANDIDATE FIELD
   Example: get_filter_options(connection_id="uuid", table_name="orders", column_name="category")
   Use the response to choose filter_type/operator.
   - If get_filter_options returns timed_out=true or repeatedly fails:
     - Do NOT keep retrying the same probe.
     - Fall back to a text filter (filter_type="text", operator="contains") and proceed.
   - Keep probing focused: prioritize high-value fields (categorical/date/numeric) and avoid probing every possible column.
   - For fields where display values differ from filter values, use label-value mapping: structure options as [{"label": "display_value", "value": "filter_value"}, ...] where label is shown in the dropdown and value is used for filtering.
   - For foreign key fields (e.g., fields ending in _id), query the referenced collection/table to get display values and create label-value pairs: [{"label": "Display Text", "value": "id_value"}, ...]

STEP 3: PERSIST FILTER METADATA (NO HTML FILTER COMPONENTS)
   Call define_dashboard_filters(filters_json=...) with correct query_id mapping.
   - Prefer omitting `id` when defining new filters; backend will assign stable IDs.
   - Use recommended operators:
     - select -> eq
     - multiselect -> in
     - date_range/number_range -> between (or gte/lte pairs)
     - text -> contains or like
   - If one logical filter should affect multiple query_id entries, create separate filter definitions per query_id.
   - Do NOT create duplicate filters for the same (query_id, field_name).
   - If a filter already exists for the same (query_id, field_name), update it (label/options/type) instead of creating a new one.
   - If the same logical field appears in multiple queries, keep one shared filter key semantics (backend handles mapping).

STEP 4: DASHBOARD HTML RULES FOR FILTERS
   DO NOT generate any filter UI/components in dashboard HTML:
   - Do NOT add FilterBar, SelectFilter, DateRangeFilter, NumberRangeFilter, TextSearchFilter
   - Do NOT add local filter state, refetchData(filterValues), or onApplyFilters wiring
   - Do NOT manually build filters/filter_values payloads in dashboard code

   Dashboard HTML should only load data normally from viewer batch endpoint.
   Host shell injects active filters into requests automatically.

USER FILTER MODIFICATIONS:

*** ADDING A NEW FILTER ***
When user asks to add a filter:
1. Call get_dashboard_filter_config() first to check existing filters (avoid duplicates)
2. Call saved_query_schema to get the SQL/Mongo query for the target query_id
3. Verify the field exists in the query's source tables/collections
4. If field DOES NOT exist in the query:
   - STOP - do NOT call save_query, define_dashboard_filters, or modify the query
   - Ask user: "Field 'X' is not in this query. Would you like me to update the query to include it?"
   - WAIT for explicit user confirmation before proceeding
5. If field EXISTS in query:
   - Use actual table names in field_name, NOT query aliases
   - Call get_filter_options(connection_id, table_name, column_name) for recommendations
   - Call define_dashboard_filters with correct query_id and field_name
   - Verify via get_dashboard_filter_config

*** UPDATING AN EXISTING FILTER ***
When user asks to change/update a filter:
1. Call get_dashboard_filter_config() to load current state
2. Identify filter_id and current config (filter_type, operator, options, query_id, field_name)
3. DO NOT modify or regenerate the saved SQL/Mongo query
4. If changing filter_type:
   - Call get_filter_options to get fresh options/recommendations
   - Update with MATCHING operator (select→"eq", multiselect→"in", date_range→"between"/"gte"/"lte", text -> contains or like)
   - Call update_dashboard_filter(filter_id, updates_json)
5. If only updating options/label/default_value (same filter_type):
   - Call get_filter_options if refreshing options from database
   - Call update_dashboard_filter(filter_id, updates_json)
6. Verify via get_dashboard_filter_config that operator matches filter_type

*** REMOVING A FILTER ***
When user asks to remove a filter:
1. Call get_dashboard_filter_config() to get filter_id
2. Call remove_dashboard_filter(filter_id)

NOTE: Regenerate dashboard HTML only if user asks for visual/layout changes (not required for metadata-only changes)

FILTER RECONCILIATION ON QUERY CHANGES:
When any saved query is modified, replaced, or new queries are added to the dashboard:
1. Call get_dashboard_filter_config() to load all current filter definitions.
2. For each modified/new query_id, call get_filter_options() on candidate source columns.
3. Stale filters (referencing query_ids or columns no longer in updated queries) MUST be removed via remove_dashboard_filter.
4. New filterable columns from changed/added queries should get new filter definitions via define_dashboard_filters.
5. Existing filters whose options may have changed should be refreshed via update_dashboard_filter.
6. Do NOT skip this reconciliation — stale filters cause runtime errors when the host shell tries to apply them.

*** FILTER CHECKLIST ***
[ ] Reviewed source schema and identified filterable source fields
[ ] Called get_dashboard_filter_config()
[ ] Called get_filter_options() where needed
[ ] Called define/update/remove dashboard filter tools to persist metadata
[ ] Confirmed generated dashboard HTML contains no filter UI components
[ ] After query changes: reconciled filters — removed stale, added new, updated changed
"""
