---
name: notion
display_name: Notion
description: Create and manage pages, databases, and blocks in Notion
emoji: "📄"
homepage: https://developers.notion.com

api:
  base_url: https://api.notion.com/v1
  domain: notion.com
  type: rest
  auth:
    type: bearer
  headers:
    Notion-Version: "2022-06-28"

credentials:
  - key: api_key
    label: API Key
    placeholder: "ntn_... or secret_..."
    help: "Internal Integration Secret from notion.so/my-integrations. Starts with 'ntn_' (newer) or 'secret_' (older)."
---

# Notion

Use the Notion API to search, create, read, and update pages, databases, and blocks.

## Setup Guide

Before using this skill, you need to create a Notion integration and grant it access to your pages:

### 1. Create an Integration

1. Go to https://www.notion.com/my-integrations
2. Click **"New integration"**
3. Name your integration (e.g., "Byaan")
4. Select the workspace you want to connect
5. Set capabilities: enable **Read content**, **Update content**, and **Insert content** as needed
6. Click **Submit** to create the integration
7. Copy the **Internal Integration Secret** (starts with `ntn_` or `secret_`)
8. Paste this key in **Settings > Skills > Notion** in the app

### 2. Grant Access to Pages

**This step is required** — integrations can only see pages explicitly shared with them.

1. Open the Notion page or database you want to access
2. Click the **"..."** menu in the top-right corner
3. Click **"Connections"** (or "Add connections")
4. Find and select your integration by name
5. Repeat for each page/database you want to access

## How Authentication Works

**You do not need to handle authentication manually.** When you call `execute_skill_api()`, the system automatically:

1. Retrieves the API key from the configured credentials
2. Adds the `Authorization: Bearer <api_key>` header
3. Adds the `Notion-Version: 2022-06-28` header

Just call the API with skill name, endpoint path, method, and body — authentication is handled for you.

## Finding Pages and Content

**When a user asks to find, read, or work with a Notion page, ALWAYS start with a search.** Never assume you know the page ID.

### Search Workflow

1. **Search by title** to find pages:

```
POST /search
{"query": "Meeting Notes"}
```

2. **Filter to pages only** (exclude databases):

```
POST /search
{
  "query": "Meeting Notes",
  "filter": {"property": "object", "value": "page"}
}
```

3. **Get recently edited pages**:

```
POST /search
{
  "query": "",
  "sort": {"direction": "descending", "timestamp": "last_edited_time"}
}
```

4. **Get all accessible pages** (empty query):

```
POST /search
{"query": ""}
```

5. **Read page content** once you have the page_id:

```
GET /blocks/{page_id}/children
```

### Search Parameters

| Parameter         | Description                                             |
| ----------------- | ------------------------------------------------------- |
| `query`           | Text to match against titles (empty string returns all) |
| `filter.property` | Always `"object"`                                       |
| `filter.value`    | `"page"` or `"database"`                                |
| `sort.direction`  | `"ascending"` or `"descending"`                         |
| `sort.timestamp`  | `"last_edited_time"`                                    |
| `page_size`       | Number of results (max 100)                             |
| `start_cursor`    | Pagination cursor from previous response                |

### Search Behavior

- Search **only returns pages/databases explicitly shared** with the integration
- Search matches **titles only**, not page content
- To search within page content, fetch blocks first then search locally
- Archived pages won't appear in search results
- Page titles are in `properties.title`, not a simple `title` field

## Common Operations

### Get a Page

```
GET /pages/{page_id}
```

### Get Page Content (Blocks)

```
GET /blocks/{page_id}/children
```

### Create a Page in a Database

```
POST /pages
{
  "parent": {"database_id": "xxx"},
  "properties": {
    "Name": {"title": [{"text": {"content": "New Item"}}]},
    "Status": {"select": {"name": "Todo"}}
  }
}
```

### Create a Standalone Page

```
POST /pages
{
  "parent": {"page_id": "parent_page_id"},
  "properties": {
    "title": {"title": [{"text": {"content": "Page Title"}}]}
  },
  "children": [
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Content here"}}]}}
  ]
}
```

### Query a Database

```
POST /databases/{database_id}/query
{
  "filter": {"property": "Status", "select": {"equals": "Active"}},
  "sorts": [{"property": "Date", "direction": "descending"}]
}
```

### Get Database Schema

```
GET /databases/{database_id}
```

### Create a Database

```
POST /databases
{
  "parent": {"page_id": "xxx"},
  "title": [{"text": {"content": "My Database"}}],
  "properties": {
    "Name": {"title": {}},
    "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}},
    "Date": {"date": {}}
  }
}
```

### Update Page Properties

```
PATCH /pages/{page_id}
{"properties": {"Status": {"select": {"name": "Done"}}}}
```

### Add Blocks to a Page

```
PATCH /blocks/{page_id}/children
{
  "children": [
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Hello"}}]}}
  ]
}
```

### Delete a Block

```
DELETE /blocks/{block_id}
```

## Property Types

Common property formats for database items:

| Type         | Format                                                   |
| ------------ | -------------------------------------------------------- |
| Title        | `{"title": [{"text": {"content": "..."}}]}`              |
| Rich text    | `{"rich_text": [{"text": {"content": "..."}}]}`          |
| Select       | `{"select": {"name": "Option"}}`                         |
| Multi-select | `{"multi_select": [{"name": "A"}, {"name": "B"}]}`       |
| Date         | `{"date": {"start": "2024-01-15", "end": "2024-01-16"}}` |
| Checkbox     | `{"checkbox": true}`                                     |
| Number       | `{"number": 42}`                                         |
| URL          | `{"url": "https://..."}}`                                |
| Email        | `{"email": "a@b.com"}`                                   |
| Relation     | `{"relation": [{"id": "page_id"}]}`                      |

## Pagination

All list endpoints support pagination:

- **`page_size`**: Number of results per request (default and max: 100)
- **`start_cursor`**: Cursor from previous response to get next page

Response includes:

- **`has_more`**: `true` if more results exist
- **`next_cursor`**: Use as `start_cursor` in next request

Example pagination flow:

```
POST /databases/{id}/query
{"page_size": 100}

# If response has "has_more": true
POST /databases/{id}/query
{"page_size": 100, "start_cursor": "next_cursor_value"}
```

## Common Pitfalls

1. **"Object not found" errors**: The integration hasn't been granted access to that page. Go to the page in Notion → "..." → "Connections" → add your integration.

2. **Search returns empty results**: Search only finds pages explicitly shared with the integration, not all pages in the workspace.

3. **Can't find page content**: `GET /pages/{id}` returns metadata only. Use `GET /blocks/{id}/children` to get the actual content.

4. **Database rows are pages**: Items in a Notion database are actually pages with `parent.type: "database_id"`. Query the database, then fetch each row's blocks if you need content.

5. **Page IDs from URLs**: Notion URLs contain the page ID at the end (32 hex chars). Convert `abc123def456...` to UUID format `abc123de-f456-...` or use without dashes — both work.

6. **Rich text arrays**: Text properties are always arrays of rich text objects, even for simple strings: `[{"text": {"content": "Hello"}}]`

## Notes

- Page/database IDs are UUIDs (with or without dashes)
- The API cannot set database view filters — that's UI-only
- Rate limit: ~3 requests/second average
- Use `is_inline: true` when creating databases to embed them in pages
