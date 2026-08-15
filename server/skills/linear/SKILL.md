---
name: linear
display_name: Linear
description: Manage issues, projects, and cycles in Linear
emoji: "⬡"
homepage: https://linear.app

api:
  base_url: https://api.linear.app
  domain: linear.app
  type: graphql
  auth:
    type: api_key

credentials:
  - key: api_key
    label: API Key
    placeholder: "lin_api_..."
    help: "Personal API key from Linear Settings → Security & Access → Personal API keys. Starts with 'lin_api_'."
---

# Linear GraphQL API

Use the Linear GraphQL API to manage issues, projects, cycles, and teams.

## Setup Guide

Before using this skill, you need to create a Personal API key in Linear:

### 1. Create an API Key

1. Open Linear and click the gear icon (Settings)
2. Navigate to **"Security & Access"** in the left sidebar
3. Scroll to **"Personal API keys"** section
4. Click **"Create key"**
5. Give it a label (e.g., "Byaan")
6. Copy the key (starts with `lin_api_`)
7. Paste this key in **Settings > Skills > Linear** in the app

## How Authentication Works

**You do not need to handle authentication manually.** When you call `execute_skill_api()`, the system automatically:

1. Retrieves the API key from the configured credentials
2. Adds the `Authorization: <api_key>` header (no Bearer prefix)
3. Sends POST request with the GraphQL query

Just call the API with skill name, endpoint path, and GraphQL query — authentication is handled for you.

## How to Call the API

Linear uses GraphQL. Call `execute_skill_api()` with these parameters:

```
execute_skill_api(
  skill_name="linear",
  endpoint_path="/graphql",
  is_graphql=True,
  graphql_query="query { viewer { id name } }",
  graphql_variables="{}"  # Optional JSON string for variables
)
```

**Parameters:**

- `skill_name`: Always `"linear"`
- `endpoint_path`: Always `"/graphql"`
- `is_graphql`: Always `True`
- `graphql_query`: The GraphQL query or mutation string
- `graphql_variables`: Optional JSON string of variables for parameterized queries

**Example with variables:**

```
execute_skill_api(
  skill_name="linear",
  endpoint_path="/graphql",
  is_graphql=True,
  graphql_query="query GetIssue($id: String!) { issue(id: $id) { title } }",
  graphql_variables="{\"id\": \"ABC-123\"}"
)
```

## Workflows

### Creating an Issue

**You must query for IDs before creating an issue.** Here's the workflow:

1. **Get team ID** (required):

```graphql
query {
  teams {
    nodes {
      id
      name
      key
    }
  }
}
```

2. **Get assignee ID** (optional):

```graphql
query {
  users {
    nodes {
      id
      name
      email
    }
  }
}
```

3. **Get workflow state ID** (optional, for non-default state):

```graphql
query {
  workflowStates(filter: { team: { id: { eq: "team-uuid" } } }) {
    nodes {
      id
      name
      type
    }
  }
}
```

4. **Create the issue**:

```graphql
mutation {
  issueCreate(
    input: {
      teamId: "team-uuid"
      title: "Fix login bug"
      description: "Users can't log in on mobile"
      priority: 2
      assigneeId: "user-uuid"
      stateId: "state-uuid"
    }
  ) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
```

### Finding Issues

Three approaches depending on what you need:

1. **Text search** — Find issues by keyword:

```graphql
query {
  issueSearch(query: "bug fix", first: 20) {
    nodes {
      id
      identifier
      title
      url
      state {
        name
      }
    }
  }
}
```

2. **Structured filter** — Find issues matching criteria:

```graphql
query {
  issues(filter: { assignee: { isMe: { eq: true } } }, first: 20) {
    nodes {
      id
      identifier
      title
      url
      state {
        name
      }
    }
  }
}
```

3. **By identifier** — Get specific issue:

```graphql
query {
  issue(id: "ABC-123") {
    id
    identifier
    title
    description
    url
    state {
      name
    }
    assignee {
      name
      email
    }
    priority
    dueDate
  }
}
```

## Filter Examples

Use the `filter` parameter to narrow results:

```graphql
# Issues assigned to current user
issues(filter: { assignee: { isMe: { eq: true } } })

# Unassigned issues
issues(filter: { assignee: { null: true } })

# High priority issues (1=Urgent, 2=High)
issues(filter: { priority: { lte: 2 } })

# Issues in specific state
issues(filter: { state: { name: { eq: "In Progress" } } })

# Issues in a specific team
issues(filter: { team: { key: { eq: "ENG" } } })

# Issues in a project
issues(filter: { project: { id: { eq: "project-uuid" } } })

# Issues with a specific label
issues(filter: { labels: { name: { eq: "bug" } } })

# Issues updated in last 7 days
issues(filter: { updatedAt: { gte: "2024-01-01T00:00:00Z" } })

# Combine filters
issues(filter: {
  and: [
    { assignee: { isMe: { eq: true } } },
    { state: { type: { eq: "started" } } }
  ]
})
```

## Pagination

Linear uses cursor-based pagination:

- **`first`**: Number of results per request (max 250)
- **`after`**: Cursor from previous response to get next page

Response includes `pageInfo`:

- **`hasNextPage`**: `true` if more results exist
- **`endCursor`**: Use as `after` in next request

**Example pagination flow:**

```graphql
# First request
query {
  issues(first: 50) {
    nodes {
      id
      identifier
      title
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}

# If hasNextPage is true, get next page
query {
  issues(first: 50, after: "cursor-from-previous-response") {
    nodes {
      id
      identifier
      title
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

## Common Queries

**Get current user:**

```graphql
query {
  viewer {
    id
    name
    email
  }
}
```

**List issues:**

```graphql
query {
  issues(first: 20) {
    nodes {
      id
      identifier
      title
      url
      state {
        name
      }
      assignee {
        name
      }
      priority
      dueDate
      createdAt
    }
  }
}
```

**Get issue by identifier:**

```graphql
query {
  issue(id: "ABC-123") {
    id
    identifier
    title
    description
    url
    state {
      name
    }
    assignee {
      name
      email
    }
    team {
      name
      key
    }
    priority
    dueDate
    labels {
      nodes {
        name
        color
      }
    }
    comments {
      nodes {
        body
        user {
          name
        }
        createdAt
      }
    }
  }
}
```

**List teams:**

```graphql
query {
  teams {
    nodes {
      id
      name
      key
    }
  }
}
```

**List projects:**

```graphql
query {
  projects(first: 20) {
    nodes {
      id
      name
      state
      url
      teams {
        nodes {
          name
        }
      }
    }
  }
}
```

**List users:**

```graphql
query {
  users {
    nodes {
      id
      name
      email
      active
    }
  }
}
```

**List workflow states for a team:**

```graphql
query {
  workflowStates(filter: { team: { key: { eq: "ENG" } } }) {
    nodes {
      id
      name
      type
    }
  }
}
```

**List labels:**

```graphql
query {
  issueLabels(first: 50) {
    nodes {
      id
      name
      color
    }
  }
}
```

## Common Mutations

**Create issue:**

```graphql
mutation {
  issueCreate(
    input: {
      teamId: "team-uuid"
      title: "Fix login bug"
      description: "Users can't log in on mobile"
      priority: 2
      dueDate: "2024-02-15"
    }
  ) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
```

**Update issue:**

```graphql
mutation {
  issueUpdate(
    id: "issue-uuid"
    input: { stateId: "state-uuid", assigneeId: "user-uuid", priority: 1 }
  ) {
    success
    issue {
      identifier
      state {
        name
      }
    }
  }
}
```

**Add label to issue:**

```graphql
mutation {
  issueAddLabel(id: "issue-uuid", labelId: "label-uuid") {
    success
    issue {
      labels {
        nodes {
          name
        }
      }
    }
  }
}
```

**Remove label from issue:**

```graphql
mutation {
  issueRemoveLabel(id: "issue-uuid", labelId: "label-uuid") {
    success
  }
}
```

**Add comment:**

```graphql
mutation {
  commentCreate(input: { issueId: "issue-uuid", body: "Fixed in PR #456" }) {
    success
    comment {
      id
      body
    }
  }
}
```

**Create label:**

```graphql
mutation {
  issueLabelCreate(
    input: { teamId: "team-uuid", name: "needs-review", color: "#ff6b6b" }
  ) {
    success
    issueLabel {
      id
      name
    }
  }
}
```

**Create project:**

```graphql
mutation {
  projectCreate(input: { name: "Q1 Roadmap", teamIds: ["team-uuid"] }) {
    success
    project {
      id
      name
      url
    }
  }
}
```

## Priority Values

Lower number = higher priority:

- 0: No priority
- 1: Urgent
- 2: High
- 3: Medium
- 4: Low

## State Types

Workflow states have these types:

- `backlog` — Not yet planned
- `unstarted` — Planned but not started
- `started` — In progress
- `completed` — Done
- `canceled` — Won't do

## Common Pitfalls

1. **identifier vs id**: Use `identifier` (e.g., "ABC-123") when querying a specific issue. Use `id` (UUID) for mutations and setting relations. The `issue(id:)` query accepts both formats.

2. **Required fields for issueCreate**: Only `teamId` and `title` are required. Query teams first to get the `teamId`.

3. **State IDs are team-specific**: Each team has its own workflow states. Query `workflowStates` for the specific team before setting `stateId`.

4. **Priority numbers are inverted**: 1 is highest priority (Urgent), 4 is lowest (Low). 0 means no priority.

5. **New issues default to Backlog**: If you don't specify `stateId`, new issues go to the team's first Backlog state.

6. **Finding IDs before mutations**: Always query for UUIDs first. You can't use identifiers like "ABC-123" for `assigneeId`, `stateId`, `labelId`, etc.

7. **Issue URL format**: Issues have a `url` field that returns the direct link to the issue in Linear. Always include it when creating or fetching issues.

8. **includeArchived parameter**: By default, archived items are excluded. Add `includeArchived: true` to include them in queries.

## Notes

- All API calls go to the single GraphQL endpoint
- Rate limit: 1,500 requests per hour
- Use `first` for pagination (max 250 per request)
- Dates use ISO 8601 format (e.g., "2024-01-15" or "2024-01-15T10:30:00Z")
- Team `key` is the short identifier shown in issue numbers (e.g., "ENG" in "ENG-123")
