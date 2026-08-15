# Build a Data-Agent Skill for This Codebase

You are tasked with analyzing this codebase's entire data layer and building a Claude Code skill that teaches AI how to write SQL/MongoDB queries against this database. The skill should be about **querying data**, not writing application code.

## Phase 1: Deep Codebase Analysis

Analyze the following in order. Be exhaustive — read every relevant file.

### 1. Database Models & Schema
- Find ALL model/schema definition files (look for ORMs like SQLAlchemy, Sequelize, Prisma, Mongoose, TypeORM, Django models, Drizzle, etc.)
- For each model/collection, document:
  - Table/collection name (actual DB name, not class name)
  - Every field: name, type, nullable, defaults, constraints
  - Primary keys, foreign keys, unique constraints
  - Indexes (single, compound, unique, partial, text)
  - Relationships (one-to-one, one-to-many, many-to-many) with join tables/foreign keys
  - Enums and their possible values
  - Soft deletes, timestamps, versioning patterns

### 2. Data Access Patterns
- Find ALL places models are queried: repositories, DAOs, services, controllers, scripts, notebooks, migrations, seeders, jobs, workers, cron tasks
- For each, document:
  - What queries are commonly run (CRUD, aggregations, joins, subqueries)
  - Filtering patterns (common WHERE clauses, date ranges, status filters)
  - Pagination approaches (offset, cursor, keyset)
  - Sorting conventions
  - Aggregation pipelines (MongoDB) or GROUP BY patterns (SQL)
  - Raw queries vs ORM usage
  - Transaction patterns
  - Bulk operations

### 3. Business Domain Context
- What do the entities represent in business terms?
- What are the core domain relationships? (e.g., "A User has many Orders, each Order has many LineItems linked to Products")
- What are the most important entities and why?
- What status flows exist? (e.g., order: pending → confirmed → shipped → delivered)
- What are the tenant/org/workspace scoping rules if any?

### 4. Query Performance & Conventions
- What indexes exist and what queries do they optimize?
- Are there any query hints, read replicas, or connection pooling patterns?
- Are there materialized views, CTEs, or complex SQL patterns?
- MongoDB: Are there aggregation pipelines? Change streams? Atlas Search?
- What are the naming conventions? (snake_case, camelCase, plural table names, etc.)

## Phase 2: Build the Skill

Create a skill file at `.claude/skills/data-agent.md` with the following structure:

~~~markdown
---
description: "Query the database — write SQL/MongoDB queries for data analysis, debugging, reporting, and exploration. Use this when asked to query data, analyze records, build reports, debug data issues, or explore the database."
---

# Data Agent Skill

## When to Use
- User asks to query, analyze, or explore data
- User asks to debug a data issue or find specific records
- User asks to build a report or aggregate data
- User asks "how many", "which", "find all", "show me" type questions about data
- User asks to write a migration or seed script that needs schema knowledge

## Database Overview
[One paragraph: what database(s) this app uses, the ORM/driver, connection details pattern]

## Complete Schema Reference

### [Table/Collection Name]
**Description:** [What this entity represents in business terms]
**Actual DB name:** `table_name`

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid/int | no | gen | Primary key |
| ... | ... | ... | ... | FK → other_table.id |

**Indexes:**
- `idx_name` on (col1, col2) — used for [what query pattern]
- unique on (tenant_id, email)

**Key relationships:**
- Has many `orders` via `orders.user_id`
- Belongs to `organization` via `org_id`

**Common filters:** status IN ('active', 'pending'), created_at ranges, tenant scoping

[Repeat for EVERY table/collection]

## Enum & Status Values
[List every enum with all possible values and what they mean]

## Relationship Map
[Describe the full entity relationship graph in text — how everything connects]

## Query Patterns & Examples

### Filtering & Scoping Rules
- [e.g., "Always filter by tenant_id when querying user-scoped data"]
- [e.g., "Soft-deleted records have deleted_at IS NOT NULL — exclude by default"]
- [e.g., "MongoDB: always use the org_id field in queries for proper index usage"]

### Common Query Templates

#### Find records with joins
```sql
-- Example: Get [entity] with related [entity]
SELECT ...
FROM ...
JOIN ... ON ...
WHERE ...
```

#### Aggregation patterns
```sql
-- Example: Count/sum/group pattern used in this codebase
SELECT ..., COUNT(*), SUM(...)
FROM ...
GROUP BY ...
```

#### MongoDB Aggregation (if applicable)
```javascript
// Example: Common pipeline pattern
db.collection.aggregate([
  { $match: { ... } },
  { $lookup: { ... } },
  { $group: { ... } }
])
```

#### Date range queries
[Show the date handling pattern this codebase uses]

#### Pagination
[Show the pagination pattern — offset, cursor, or keyset]

#### Full-text search (if applicable)
[Show search query patterns]

### Performance Rules
- [e.g., "Always use index on (org_id, created_at) for time-range queries"]
- [e.g., "Avoid SELECT * on the events table — it has 50+ columns, select only what's needed"]
- [e.g., "The orders table has 10M+ rows — always use indexed columns in WHERE"]

### Anti-Patterns to Avoid
- [e.g., "Never query without tenant scoping"]
- [e.g., "Don't use $regex on unindexed MongoDB fields"]
- [e.g., "Avoid N+1 — use JOINs or $lookup instead of looping"]

## Database-Specific Notes
[Any DB-specific syntax, functions, or features this codebase relies on — e.g., PostgreSQL JSONB operators, MongoDB's $facet, MySQL's GROUP_CONCAT, SQLite limitations]
~~~

## Important Rules

1. **Read every single model file.** Don't skip any. Don't summarize — be exhaustive.
2. **Read how models are actually used** — don't just document the schema, document the query patterns from real code (services, repositories, controllers, scripts).
3. **Use actual table/collection names** as they appear in the database, not ORM class names.
4. **Include real examples** from the codebase, adapted into standalone query form.
5. **The skill teaches querying, not coding.** Don't include ORM syntax, API endpoints, or application logic. Focus on raw SQL / MongoDB shell queries.
6. **Test your understanding** — after building the skill, verify it by cross-referencing at least 3 complex queries from the codebase to make sure your schema documentation would enable someone to write them.
7. **If the codebase uses multiple databases** (e.g., PostgreSQL + Redis + MongoDB), document each separately with clear sections.
8. **Keep the skill file under 1000 lines** — be dense and precise, not verbose. Use tables for schemas, not paragraphs.
