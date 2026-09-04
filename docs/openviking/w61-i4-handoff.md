# W6.1 OpenViking I4 Handoff

## Provider

- Hosted base URL: `https://api.vikingdb.cn-beijing.volces.com/openviking`
- API key source: runtime environment/approved secret source only.
- Browser never receives or stores the API key.
- OpenViking is not self-deployed and is not registered as a Connection or MCP.

## ResourceRef

`ResourceRef` is an opaque, signed, profile-scoped capability:

`ovr_<base64url({"p":"<profile_id>","u":"viking://resources/<path>"})>.<hmac-sha256>`

The HMAC key is derived from `OPENVIKING_PROFILE_ENCRYPTION_KEY` inside the BFF and never leaves the server. The reference contains no API key and no file content. Profile lookup is tenant/owner scoped before resolution, and the BFF rejects invalid signatures, another profile, another tenant/owner, and untrusted URI schemes.

## I4 BFF endpoints

All endpoints are under `/api/knowledge/openviking`, authenticated by the existing Data Studio `AuthContext` and tenant scope:

- `GET /profiles`: profile status and safe metadata.
- `POST /profiles/{profile_id}/resource/resolve`: validate a ResourceRef and return safe stat metadata.
- `POST /profiles/{profile_id}/resource/read`: read content through the BFF. The JSON body contains `resource_ref`; optional `offset` and `limit` are query parameters.
- `POST /profiles/{profile_id}/operations/fs_list`: resource tree/list.
- `POST /profiles/{profile_id}/operations/search` and `/find`: retrieval.
- `POST /profiles/{profile_id}/text`, `/upload`, and `/operations/resource_import`: imports.
- `GET /api/datasources`: discover `source_type=source_resource` records for Connection-source import.
- `POST /profiles/{profile_id}/connection-resource`: import a ready Source Resource by server-side `resource_id`; caller-supplied connection documents are not accepted.

Browser calls use the normal Data Studio session or `Authorization: Bearer <DATA_STUDIO_TOKEN>` plus `X-Tenant-ID` when selecting a tenant. Server-to-server I4 callers use the same Data Studio authentication. The BFF resolves opaque refs to upstream `uri`, adds the OpenViking `X-API-Key` server-side, and recursively redacts credential, token, owner, account, and internal URI fields from responses.

## Response and errors

Responses use the existing `{success, message, data}` envelope. On failure, `data` contains `{code, message}`. Resource data uses `resource_ref`, safe display metadata, and bounded content. Stable errors include:

- `INVALID_RESOURCE_REF` (422)
- `RESOURCE_OUT_OF_SCOPE` (403)
- `OPENVIKING_CONTEXT_FORBIDDEN` (403)
- `OPENVIKING_NOT_FOUND` (404)
- `OPENVIKING_AUTH_FAILED` (401)
- `OPENVIKING_TIMEOUT` (504)
- `OPENVIKING_UNAVAILABLE` (502)

Timeouts are bounded by `OPENVIKING_TIMEOUT_SECONDS` and map to `OPENVIKING_TIMEOUT` (504). Read operations may be retried with bounded backoff. Mutating operations use a BFF profile/tenant scoped idempotency key derived from the normalized request, so retrying the same request returns the stored result instead of repeating the upstream write.

## Example

```json
{
  "profile_id": "ov_example",
  "resource_ref": "ovr_<opaque-payload>.<signature>"
}
```

Only the BFF may resolve this value. Revoking the profile removes the lookup capability, so subsequent resolve/read calls fail closed with 404.
