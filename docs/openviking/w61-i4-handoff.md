# W6.1 OpenViking I4 Handoff

## Provider

- Hosted base URL: `https://api.vikingdb.cn-beijing.volces.com/openviking`
- API key source: runtime environment/approved secret source only.
- Browser never receives or stores the API key.
- OpenViking is not self-deployed and is not registered as a Connection or MCP.

## ResourceRef

`ResourceRef` is an opaque, profile-scoped value:

`ovr_<base64url({"p":"<profile_id>","u":"viking://resources/<path>"})>.<hmac-sha256>`

The HMAC key is derived from `OPENVIKING_PROFILE_ENCRYPTION_KEY` inside the BFF and never leaves the server. The reference contains no API key and no file content. The BFF rejects invalid signatures, another profile, another tenant, and paths outside the profile workspace.

## I4 BFF endpoints

All endpoints are under `/api/knowledge/openviking`, authenticated by the existing Data Studio `AuthContext` and tenant scope:

- `GET /profiles`: profile status and safe metadata.
- `POST /profiles/{profile_id}/resource/resolve`: validate a ResourceRef and return safe stat metadata.
- `POST /profiles/{profile_id}/resource/read`: read content through the BFF. Body contains `resource_ref`; optional `offset` and `limit` are query parameters.
- `POST /profiles/{profile_id}/operations/fs_list`: resource tree/list.
- `POST /profiles/{profile_id}/operations/search` and `/find`: retrieval.
- `POST /profiles/{profile_id}/text`, `/upload`, and `/operations/resource_import`: imports.

The BFF resolves opaque refs to upstream `uri`, adds `X-API-Key` server-side, and recursively redacts credential, token, owner, account, and internal URI fields from responses.

## Response and errors

Responses use the existing `{success, message, data}` envelope. Resource data uses `resource_ref`, safe display metadata, and bounded content. Stable errors include:

- `INVALID_RESOURCE_REF` (422)
- `RESOURCE_OUT_OF_SCOPE` (403)
- `OPENVIKING_CONTEXT_FORBIDDEN` (403)
- `OPENVIKING_NOT_FOUND` (404)
- `OPENVIKING_AUTH_FAILED` (401)
- `OPENVIKING_TIMEOUT` (504)
- `OPENVIKING_UNAVAILABLE` (502)

Timeouts are bounded by `OPENVIKING_TIMEOUT_SECONDS`. Idempotent writes use the BFF profile/tenant scoped idempotency store; callers may retry failed requests without exposing credentials.
